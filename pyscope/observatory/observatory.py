import configparser
import datetime
import glob
import importlib
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
from ast import literal_eval
from datetime import datetime
from pathlib import Path

import numpy as np
import tqdm
from astropy import coordinates as coord
from astropy import time as astrotime
from astropy import units as u
from astropy import wcs as astropywcs
from astropy.io import fits
from astroquery.mpc import MPC
from scipy.optimize import curve_fit

from .. import __version__, observatory
from ..analysis import detect_sources_photutils
from ..utils import _kwargs_to_config, airmass
from . import ObservatoryException
from .ascom_device import ASCOMDevice
from .device import Device

logger = logging.getLogger(__name__)


class Observatory:
    def __init__(self, config_path=None, **kwargs):
        logger.debug("Observatory.__init__() called")
        logger.debug("config_path: %s" % config_path)
        logger.debug("kwargs: %s" % kwargs)

        # TODO: Add allowed_overwrite keys to config file and parser to check which keys can be overwritten (especially from MaxIm).
        self._config = configparser.ConfigParser()
        self._config["site"] = {}
        self._config["camera"] = {}
        self._config["cover_calibrator"] = {}
        self._config["dome"] = {}
        self._config["filter_wheel"] = {}
        self._config["focuser"] = {}
        self._config["observing_conditions"] = {}
        self._config["rotator"] = {}
        self._config["safety_monitor"] = {}
        self._config["switch"] = {}
        self._config["telescope"] = {}
        self._config["autofocus"] = {}

        self._site_name = "pyscope Site"
        self._instrument_name = "pyscope Instrument"
        self._instrument_description = (
            "pyscope is a pure-Python telescope control package."
        )
        self._latitude = "00d00m00.00000s"
        self._longitude = "00d00m00.00000s"
        self._elevation = 0.0
        self._diameter = 0.0
        self._focal_length = 0.0

        self._camera = ""
        self._camera_driver = ""
        self._camera_kwargs = []
        self._cooler_setpoint = 0.0
        self._cooler_tolerance = 0.0
        self._max_dimension = 0

        self._cover_calibrator = ""
        self._cover_calibrator_driver = ""
        self._cover_calibrator_kwargs = []
        self._cover_calibrator_alt = 0.0
        self._cover_calibrator_az = 0.0

        self._dome = ""
        self._dome_driver = ""
        self._dome_kwargs = []

        self._filter_wheel = ""
        self._filter_wheel_driver = ""
        self._filter_wheel_kwargs = []
        self._filters = []
        self._filter_focus_offsets = []

        self._focuser = None
        self._focuser_driver = None
        self._focuser_kwargs = None

        self._observing_conditions = None
        self._observing_conditions_driver = None
        self._observing_conditions_kwargs = None

        self._rotator = None
        self._rotator_driver = None
        self._rotator_kwargs = None
        self._rotator_reverse = False
        self._rotator_min_angle = None
        self._rotator_max_angle = None

        self._safety_monitor = []
        self._safety_monitor_driver = []
        self._safety_monitor_kwargs = []

        self._switch = []
        self._switch_driver = []
        self._switch_kwargs = []

        self._telescope = None
        self._telescope_driver = None
        self._telescope_kwargs = None
        self._min_altitude = 10 * u.deg
        self._settle_time = 5

        self._autofocus = None
        self._autofocus_driver = None
        self._autofocus_kwargs = None

        self._slew_rate = None
        self._instrument_reconfig_times = None

        self._maxim = None

        if not os.path.exists(config_path):
            raise ObservatoryException("Config file '%s' not found" % config_path)

        if config_path is not None:
            logger.info(
                "Using this config file to initialize the observatory: %s" % config_path
            )
            try:
                self._config.read(config_path)
            except:
                raise ObservatoryException(
                    "Error parsing config file '%s'" % config_path
                )

            # Camera
            self._camera_driver = self._config["camera"]["camera_driver"]
            self._camera_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "camera", "camera_kwargs", fallback=""
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get("camera", "camera_kwargs", fallback=None)
                not in (None, "")
                else None
            )
            if self.camera_driver.lower() in ("maxim", "maximdl", "_maximcamera"):
                logger.info("Using MaxIm DL as the camera driver")
                self._maxim = _import_driver("Maxim")
                self._camera = self._maxim.camera
            else:
                self._camera = _import_driver(
                    self.camera_driver, kwargs=self.camera_kwargs
                )

            # Cover calibrator
            self._cover_calibrator_driver = self._config.get(
                "cover_calibrator", "cover_calibrator_driver", fallback=None
            )
            self._cover_calibrator_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "cover_calibrator", "cover_calibrator_kwargs", fallback=""
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get(
                    "cover_calibrator", "cover_calibrator_kwargs", fallback=None
                )
                not in (None, "")
                else None
            )
            self._cover_calibrator = _import_driver(
                self.cover_calibrator_driver,
                kwargs=self.cover_calibrator_kwargs,
            )

            # Dome
            self._dome_driver = self._config.get("dome", "dome_driver", fallback=None)
            self._dome_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get("dome", "dome_kwargs", fallback="")
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get("dome", "dome_kwargs", fallback=None)
                not in (None, "")
                else None
            )
            self._dome = _import_driver(self.dome_driver, kwargs=self.dome_kwargs)

            # Filter wheel
            self._filter_wheel_driver = self._config.get(
                "filter_wheel", "filter_wheel_driver", fallback=None
            )
            self._filter_wheel_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "filter_wheel", "filter_wheel_kwargs", fallback=""
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get(
                    "filter_wheel", "filter_wheel_kwargs", fallback=None
                )
                not in (None, "")
                else None
            )
            if self.filter_wheel_driver.lower() in (
                "maxim",
                "maximdl",
                "_maximfilterwheel",
            ):
                if self._maxim is None:
                    raise ObservatoryException(
                        "MaxIm DL must be used as the camera driver when using MaxIm DL as the filter wheel driver."
                    )
                logger.info("Using MaxIm DL as the filter wheel driver")
                self._filter_wheel = self._maxim._filter_wheel
            else:
                self._filter_wheel = _import_driver(
                    self.filter_wheel_driver,
                    kwargs=self.filter_wheel_kwargs,
                )

            # Focuser
            self._focuser_driver = self._config.get(
                "focuser", "focuser_driver", fallback=None
            )
            self._focuser_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "focuser", "focuser_kwargs", fallback=""
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get("focuser", "focuser_kwargs", fallback=None)
                not in (None, "")
                else None
            )
            self._focuser = _import_driver(
                self.focuser_driver,
                kwargs=self.focuser_kwargs,
            )

            # Observing conditions
            self._observing_conditions_driver = self._config.get(
                "observing_conditions", "observing_conditions_driver", fallback=None
            )
            self._observing_conditions_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "observing_conditions",
                            "observing_conditions_kwargs",
                            fallback="",
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get(
                    "observing_conditions", "observing_conditions_kwargs", fallback=None
                )
                not in (None, "")
                else None
            )
            self._observing_conditions = _import_driver(
                self.observing_conditions_driver,
                kwargs=self.observing_conditions_kwargs,
            )

            # Rotator
            self._rotator_driver = self._config.get(
                "rotator", "rotator_driver", fallback=None
            )
            self._rotator_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "rotator", "rotator_kwargs", fallback=""
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get("rotator", "rotator_kwargs", fallback=None)
                not in (None, "")
                else None
            )
            self._rotator = _import_driver(
                self.rotator_driver,
                kwargs=self.rotator_kwargs,
            )

            # Safety monitor
            for val in self._config["safety_monitor"].values():
                if val == "":
                    continue
                try:
                    split_val = val.replace(" ", "").split(",")
                    self._safety_monitor_driver.append(split_val[0])
                    if len(split_val) > 1:
                        kw = split_val[1:]
                        self._safety_monitor_kwargs.append(
                            dict(
                                (k, literal_eval(v))
                                for k, v in (pair.split("=") for pair in kw)
                            )
                        )
                    else:
                        self._safety_monitor_kwargs.append(None)
                    self._safety_monitor.append(
                        _import_driver(
                            self._safety_monitor_driver[-1],
                            kwargs=self.safety_monitor_kwargs[-1],
                        )
                    )
                except:
                    logger.warning("Error parsing safety monitor config: %s" % val)

            # Switch
            for val in self._config["switch"].values():
                if val == "":
                    continue
                try:
                    split_val = val.replace(" ", "").split(",")
                    self._switch_driver.append(split_val[0])
                    if len(split_val) > 1:
                        kw = split_val[1:]
                        self._switch_kwargs.append(
                            dict(
                                (k, literal_eval(v))
                                for k, v in (pair.split("=") for pair in kw)
                            )
                        )
                    else:
                        self._switch_kwargs.append(None)
                    self._switch.append(
                        _import_driver(
                            self._switch_driver[-1],
                            kwargs=self.switch_kwargs[-1],
                        )
                    )
                except:
                    logger.warning("Error parsing switch config: %s" % val)

            # Telescope
            self._telescope_driver = self._config["telescope"]["telescope_driver"]
            self._telescope_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "telescope", "telescope_kwargs", fallback=""
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get("telescope", "telescope_kwargs", fallback=None)
                not in (None, "")
                else None
            )
            self._telescope = _import_driver(
                self.telescope_driver,
                kwargs=self.telescope_kwargs,
            )

            # Autofocus
            self._autofocus_driver = self._config.get(
                "autofocus", "autofocus_driver", fallback=None
            )
            self._autofocus_kwargs = (
                dict(
                    (k, literal_eval(v))
                    for k, v in (
                        pair.split("=")
                        for pair in self._config.get(
                            "autofocus", "autofocus_kwargs", fallback=""
                        )
                        .replace(" ", "")
                        .split(",")
                    )
                )
                if self._config.get("autofocus", "autofocus_kwargs", fallback=None)
                not in (None, "")
                else None
            )
            if self.autofocus_driver.lower() in ("maxim", "maximdl"):
                if self._maxim is None:
                    raise ObservatoryException(
                        "MaxIm DL must be used as the camera driver when using MaxIm DL as the autofocus driver."
                    )
                self._autofocus = self._maxim.autofocus
                logger.info("Using MaxIm DL as the autofocus driver")
            else:
                self._autofocus = _import_driver(
                    self.autofocus_driver,
                    kwargs=self.autofocus_kwargs,
                )

            # Get other keywords from config file
            logger.debug("Reading other keywords from config file")
            master_dict = {
                **self._config["site"],
                **self._config["camera"],
                **self._config["cover_calibrator"],
                **self._config["dome"],
                **self._config["filter_wheel"],
                **self._config["focuser"],
                **self._config["observing_conditions"],
                **self._config["rotator"],
                **self._config["safety_monitor"],
                **self._config["switch"],
                **self._config["telescope"],
                **self._config["autofocus"],
                **self._config["scheduling"],
            }
            logger.debug("Master dict: %s" % master_dict)
            self._read_out_kwargs(master_dict)
            logger.debug("Finished reading other keywords from config file")

        logger.info("Checking passed kwargs and overriding config file values")

        # Camera
        self._camera = kwargs.get("camera", self._camera)
        _check_class_inheritance(type(self._camera), "Camera")
        self._camera_driver = self._camera.__class__.__name__
        self._camera_kwargs = kwargs.get("camera_kwargs", self._camera_kwargs)
        self._config["camera"]["camera_driver"] = self._camera_driver
        self._config["camera"]["camera_kwargs"] = _kwargs_to_config(self._camera_kwargs)

        # Cover calibrator
        self._cover_calibrator = kwargs.get("cover_calibrator", self._cover_calibrator)
        if self._cover_calibrator is not None:
            _check_class_inheritance(type(self._cover_calibrator), "CoverCalibrator")
            self._cover_calibrator_driver = self._cover_calibrator.__class__.__name__
            self._cover_calibrator_kwargs = kwargs.get(
                "cover_calibrator_kwargs", self._cover_calibrator_kwargs
            )
            self._config["cover_calibrator"][
                "cover_calibrator_driver"
            ] = self._cover_calibrator_driver
            self._config["cover_calibrator"]["cover_calibrator_kwargs"] = (
                _kwargs_to_config(self._cover_calibrator_kwargs)
            )

        # Dome
        self._dome = kwargs.get("dome", self._dome)
        if self._dome is not None:
            _check_class_inheritance(type(self._dome), "Dome")
            self._dome_driver = self._dome.__class__.__name__
            self._dome_kwargs = kwargs.get("dome_kwargs", self._dome_kwargs)
            self._config["dome"]["dome_driver"] = self._dome_driver
            self._config["dome"]["dome_kwargs"] = _kwargs_to_config(self._dome_kwargs)

        # Filter wheel
        self._filter_wheel = kwargs.get("filter_wheel", self._filter_wheel)
        if self._filter_wheel is not None:
            _check_class_inheritance(type(self._filter_wheel), "FilterWheel")
            self._filter_wheel_driver = self._filter_wheel.__class__.__name__
            self._filter_wheel_kwargs = kwargs.get(
                "filter_wheel_kwargs", self._filter_wheel_kwargs
            )
            self._config["filter_wheel"][
                "filter_wheel_driver"
            ] = self._filter_wheel_driver
            self._config["filter_wheel"]["filter_wheel_kwargs"] = _kwargs_to_config(
                self._filter_wheel_kwargs
            )

        # Focuser
        self._focuser = kwargs.get("focuser", self._focuser)
        if self._focuser is not None:
            _check_class_inheritance(type(self._focuser), "Focuser")
            self._focuser_driver = self._focuser.__class__.__name__
            self._focuser_kwargs = kwargs.get("focuser_kwargs", self._focuser_kwargs)
            self._config["focuser"]["focuser_driver"] = self._focuser_driver
            self._config["focuser"]["focuser_kwargs"] = _kwargs_to_config(
                self._focuser_kwargs
            )

        # Observing conditions
        self._observing_conditions = kwargs.get(
            "observing_conditions", self._observing_conditions
        )
        if self._observing_conditions is not None:
            _check_class_inheritance(
                type(self._observing_conditions), "ObservingConditions"
            )
            self._observing_conditions_driver = (
                self._observing_conditions.__class__.__name__
            )
            self._observing_conditions_kwargs = kwargs.get(
                "observing_conditions_kwargs", self._observing_conditions_kwargs
            )
            self._config["observing_conditions"][
                "observing_conditions_driver"
            ] = self._observing_conditions_driver
            self._config["observing_conditions"]["observing_conditions_kwargs"] = (
                _kwargs_to_config(self._observing_conditions_kwargs)
            )

        # Rotator
        self._rotator = kwargs.get("rotator", self._rotator)
        if self._rotator is not None:
            _check_class_inheritance(type(self._rotator), "Rotator")
            self._rotator_driver = self._rotator.__class__.__name__
            self._rotator_kwargs = kwargs.get("rotator_kwargs", self._rotator_kwargs)
            self._config["rotator"]["rotator_driver"] = self._rotator_driver
            self._config["rotator"]["rotator_kwargs"] = _kwargs_to_config(
                self._rotator_kwargs
            )

        # Safety monitor
        kwarg = kwargs.get("safety_monitor", self._safety_monitor)
        if type(kwarg) not in (iter, list, tuple):
            self._safety_monitor = kwarg
            if self._safety_monitor is not None:
                _check_class_inheritance(type(self._safety_monitor), "SafetyMonitor")
                self._safety_monitor_driver = self._safety_monitor.__class__.__name__
                self._safety_monitor_kwargs = kwargs.get(
                    "safety_monitor_kwargs", self._safety_monitor_kwargs
                )
                self._config["safety_monitor"]["driver_0"] = (
                    self._safety_monitor_driver
                    + ","
                    + _kwargs_to_config(self._safety_monitor_kwargs)
                )
        else:
            self._safety_monitor = kwarg
            for i, safety_monitor in enumerate(self._safety_monitor):
                if safety_monitor is not None:
                    _check_class_inheritance(type(safety_monitor), "SafetyMonitor")
                    self._safety_monitor_driver[i] = safety_monitor.__class__.__name__
                    self._safety_monitor_kwargs[i] = (
                        kwargs.get(
                            "safety_monitor_kwargs", self._safety_monitor_kwargs
                        )[i]
                        if kwargs.get(
                            "safety_monitor_kwargs", self._safety_monitor_kwargs[i]
                        )
                        is not None
                        else None
                    )
                    self._config["safety_monitor"]["driver_%i" % i] = (
                        self._safety_monitor_driver[i]
                        + ","
                        + _kwargs_to_config(self._safety_monitor_kwargs[i])
                    )

        # Switch
        kwarg = kwargs.get("switch", self._switch)
        if type(kwarg) not in (iter, list, tuple):
            self._switch = kwarg
            if self._switch is not None:
                _check_class_inheritance(type(self._switch), "Switch")
                self._switch_driver = self._switch.__class__.__name__
                self._switch_kwargs = kwargs.get("switch_kwargs", self._switch_kwargs)
                self._config["switch"]["driver_0"] = (
                    self._switch_driver + "," + _kwargs_to_config(self._switch_kwargs)
                )
        else:
            self._switch = kwarg
            for i, switch in enumerate(self._switch):
                if switch is not None:
                    _check_class_inheritance(type(switch), "Switch")
                    self._switch_driver[i] = switch.__class__.__name__
                    self._switch_kwargs[i] = (
                        kwargs.get("switch_kwargs", self._switch_kwargs[i])
                        if kwargs.get("switch_kwargs", self._switch_kwargs[i])
                        is not None
                        else None
                    )
                    self._config["switch"]["driver_%i" % i] = (
                        self._switch_driver[i]
                        + ","
                        + _kwargs_to_config(self._switch_kwargs[i])
                    )

        # Telescope
        self._telescope = kwargs.get("telescope", self._telescope)
        _check_class_inheritance(type(self._telescope), "Telescope")
        self._telescope_driver = self._telescope.__class__.__name__
        self._telescope_kwargs = kwargs.get("telescope_kwargs", self._telescope_kwargs)
        self._config["telescope"]["telescope_driver"] = self._telescope_driver
        self._config["telescope"]["telescope_kwargs"] = _kwargs_to_config(
            self._telescope_kwargs
        )

        # Autofocus
        self._autofocus = kwargs.get("autofocus", self._autofocus)
        if self._autofocus is not None:
            _check_class_inheritance(type(self._autofocus), "Autofocus")
            self._autofocus_driver = self._autofocus.__class__.__name__
            self._autofocus_kwargs = kwargs.get(
                "autofocus_kwargs", self._autofocus_kwargs
            )
            self._config["autofocus"]["autofocus_driver"] = self._autofocus_driver
            self._config["autofocus"]["autofocus_kwargs"] = _kwargs_to_config(
                self._autofocus_kwargs
            )

        logger.debug("Reading out keywords passed as kwargs")
        logger.debug("kwargs: %s" % kwargs)
        self._read_out_kwargs(kwargs)
        logger.debug("kwargs read out")

        # Non-keyword attributes
        self._last_camera_shutter_status = None
        self.camera.OriginalStartExposure = self.camera.StartExposure

        def NewStartExposure(Duration, Light):
            self._last_camera_shutter_status = Light
            self.camera.OriginalStartExposure(Duration, Light)

        self.camera.StartExposure = NewStartExposure

        self._current_focus_offset = 0

        # Threads
        self._observing_conditions_thread = None
        self._observing_conditions_event = None

        self._safety_monitor_thread = None
        self._safety_monitor_event = None

        self._derotation_thread = None
        self._derotation_event = None

        logger.debug("Config:")
        logger.debug(self._config)

    def connect_all(self):
        logger.debug("Observatory.connect_all() called")

        self.camera.Connected = True
        if self.camera.Connected:
            logger.info("Camera connected")
        else:
            logger.warning("Camera failed to connect")
        if self.camera.CanSetCCDTemperature and self.cooler_setpoint is not None:
            logger.info("Turning cooler on")
            self.camera.CoolerOn = True

        if self.cover_calibrator is not None:
            self.cover_calibrator.Connected = True
            if self.cover_calibrator.Connected:
                logger.info("Cover calibrator connected")
            else:
                logger.warning("Cover calibrator failed to connect")

        if self.dome is not None:
            self.dome.Connected = True
            if self.dome.Connected:
                logger.info("Dome connected")
            else:
                logger.warning("Dome failed to connect")

        if self.filter_wheel is not None:
            self.filter_wheel.Connected = True
            if self.filter_wheel.Connected:
                logger.info("Filter wheel connected")
            else:
                logger.warning("Filter wheel failed to connect")

        if self.focuser is not None:
            self.focuser.Connected = True
            if self.focuser.Connected:
                logger.info("Focuser connected")
            else:
                logger.warning("Focuser failed to connect")

        if self.observing_conditions is not None:
            self.observing_conditions.Connected = True
            if self.observing_conditions.Connected:
                logger.info("Observing conditions connected")
            else:
                logger.warning("Observing conditions failed to connect")

        if self.rotator is not None:
            self.rotator.Connected = True
            if self.rotator.Connected:
                logger.info("Rotator connected")
            else:
                logger.warning("Rotator failed to connect")

        if self.safety_monitor is not None:
            for safety_monitor in self.safety_monitor:
                safety_monitor.Connected = True
                if safety_monitor.Connected:
                    logger.info("Safety monitor %s connected" % safety_monitor.Name)
                else:
                    logger.warning(
                        "Safety monitor %s failed to connect" % safety_monitor.Name
                    )

        if self.switch is not None:
            for switch in self.switch:
                switch.Connected = True
                if switch.Connected:
                    logger.info("Switch %s connected" % switch.Name)
                else:
                    logger.warning("Switch %s failed to connect" % switch.Name)

        self.telescope.Connected = True
        if self.telescope.Connected:
            logger.info("Telescope connected")
        else:
            logger.warning("Telescope failed to connect")

        logger.info("Unparking telescope...")
        try:
            self.telescope.Unpark()
            logger.info("Telescope unparked")
        except:
            self.telescope.Unpark
            logger.info("Telescope unparked")

        return True

    def disconnect_all(self):
        """Disconnects from the observatory"""

        logger.debug("Observatory.disconnect_all() called")
        # TODO: Implement safe warmup procedure
        if self.camera.CoolerOn:
            self.camera.CoolerOn = False
        self.camera.Connected = False
        if not self.camera.Connected:
            logger.info("Camera disconnected")
        else:
            logger.warning("Camera failed to disconnect")

        if self.cover_calibrator is not None:
            self.cover_calibrator.Connected = False
            if not self.cover_calibrator.Connected:
                logger.info("Cover calibrator disconnected")
            else:
                logger.warning("Cover calibrator failed to disconnect")

        if self.dome is not None:
            self.dome.Connected = False
            if not self.dome.Connected:
                logger.info("Dome disconnected")
            else:
                logger.warning("Dome failed to disconnect")

        if self.filter_wheel is not None:
            self.filter_wheel.Connected = False
            if not self.filter_wheel.Connected:
                logger.info("Filter wheel disconnected")
            else:
                logger.warning("Filter wheel failed to disconnect")

        if self.focuser is not None:
            self.focuser.Connected = False
            if not self.focuser.Connected:
                logger.info("Focuser disconnected")
            else:
                logger.warning("Focuser failed to disconnect")

        if self.observing_conditions is not None:
            self.observing_conditions.Connected = False
            if not self.observing_conditions.Connected:
                logger.info("Observing conditions disconnected")
            else:
                logger.warning("Observing conditions failed to disconnect")

        if self.rotator is not None:
            self.rotator.Connected = False
            if not self.rotator.Connected:
                logger.info("Rotator disconnected")
            else:
                logger.warning("Rotator failed to disconnect")

        if self.safety_monitor is not None:
            for safety_monitor in self.safety_monitor:
                safety_monitor.Connected = False
                if not safety_monitor.Connected:
                    logger.info("Safety monitor %s disconnected" % safety_monitor.Name)
                else:
                    logger.warning(
                        "Safety monitor %s failed to disconnect" % safety_monitor.Name
                    )

        if self.switch is not None:
            for switch in self.switch:
                switch.Connected = False
                if not switch.Connected:
                    logger.info("Switch %s disconnected" % switch.Name)
                else:
                    logger.warning("Switch %s failed to disconnect" % switch.Name)

        self.telescope.Connected = False
        if not self.telescope.Connected:
            logger.info("Telescope disconnected")
        else:
            logger.warning("Telescope failed to disconnect")

        return True

    def shutdown(self):
        """Shuts down the observatory"""

        logger.info("Shutting down observatory")

        if self.camera.CanAbortExposure:
            logger.info("Aborting any in-progress camera exposures...")
            try:
                self.camera.AbortExposure()
                logger.info("Camera exposure aborted")
            except:
                logger.exception("Error aborting exposure during shutdown")

        logger.info("Attempting to take a dark exposure to close camera shutter...")
        try:
            self.camera.StartExposure(0, False)
            while self.camera.ImageReady is False:
                time.sleep(0.1)
            logger.info("Dark exposure complete")
        except:
            logger.exception("Error closing camera shutter during shutdown")

        if self.cover_calibrator is not None:
            if self.cover_calibrator.CalibratorState != "NotPresent":
                logger.info("Attempting to turn off cover calibrator...")
                try:
                    self.cover_calibrator.CalibratorOff()
                    logger.info("Cover calibrator turned off")
                except:
                    logger.exception(
                        "Error turning off cover calibrator during shutdown"
                    )
            if self.cover_calibrator.CoverState != "NotPresent":
                logger.info("Attempting to halt any cover calibrator shutter motion...")
                try:
                    self.cover_calibrator.HaltCover()
                    logger.info("Cover calibrator shutter motion halted")
                except:
                    logger.exception(
                        "Error closing cover calibrator shutter during shutdown"
                    )
                logger.info("Attempting to close cover calibrator shutter...")
                try:
                    self.cover_calibrator.CloseCover()
                    logger.info("Cover calibrator shutter closed")
                except:
                    logger.exception(
                        "Error closing cover calibrator shutter during shutdown"
                    )

        if self.dome is not None:
            logger.info("Aborting any dome motion...")
            try:
                self.dome.AbortSlew()
                logger.info("Dome motion aborted")
            except:
                logger.exception("Error aborting dome motion during shutdown")

            logger.info("Attempting to park dome...")
            try:
                self.dome.Park()
                logger.info("Dome parked")
            except:
                logger.exception("Error parking dome during shutdown")

            if self.dome.CanSetShutter:
                logger.info("Attempting to close dome shutter...")
                try:
                    self.dome.CloseShutter()
                    logger.info("Dome shutter closed")
                except:
                    logger.exception("Error closing dome shutter during shutdown")

        if self.focuser is not None:
            logger.info("Aborting any in-progress focuser motion...")
            try:
                self.focuser.Halt()
                logger.info("Focuser motion aborted")
            except:
                logger.exception("Error aborting focuser motion during shutdown")

        if self.rotator is not None:
            logger.info("Aborting any in-progress rotator motion...")
            try:
                self.rotator.Halt()
                logger.info("Rotator motion aborted")
            except:
                logger.exception("Error stopping rotator during shutdown")

        logger.info("Aborting any in-progress telescope slews...")
        try:
            self.telescope.AbortSlew()
            logger.info("Telescope slew aborted")
        except:
            logger.exception("Error aborting slew during shutdown")

        logger.info("Attempting to turn off telescope tracking...")
        try:
            self.telescope.DeclinationRate = 0
            self.telescope.RightAscensionRate = 0
            self.telescope.Tracking = False
            logger.info("Telescope tracking turned off")
        except:
            logger.exception("Error turning off telescope tracking during shutdown")

        if self.telescope.CanPark:
            logger.info("Attempting to park telescope...")
            try:
                self.telescope.Park()
                logger.info("Telescope parked")
            except:
                logger.exception("Error parking telescope during shutdown")
        elif self.telescope.CanFindHome:
            logger.info("Attempting to find home position...")
            try:
                self.telescope.FindHome()
                logger.info("Telescope home position found")
            except:
                logger.exception("Error finding home position during shutdown")

        return True

    def lst(self, t=None):
        """Returns the local sidereal time"""

        logger.debug(f"Observatory.lst({t}) called")

        if t is None:
            t = self.observatory_time
        else:
            t = astrotime.Time(t)
        return t.sidereal_time("apparent", self.observatory_location).to("hourangle")

    def sun_altaz(self, t=None):
        """Returns the altitude of the sun"""

        logger.debug(f"Observatory.sun_altaz({t}) called")

        if t is None:
            t = self.observatory_time
        else:
            t = astrotime.Time(t)

        sun = coord.get_sun(t).transform_to(
            coord.AltAz(obstime=t, location=self.observatory_location)
        )

        return (sun.alt.deg, sun.az.deg)

    def moon_altaz(self, t=None):
        """Returns the current altitude of the moon"""

        logger.debug(f"Observatory.moon_altaz({t}) called")

        if t is None:
            t = self.observatory_time
        else:
            t = astrotime.Time(t)

        moon = coord.get_body("moon", t).transform_to(
            coord.AltAz(obstime=t, location=self.observatory_location)
        )

        return (moon.alt.deg, moon.az.deg)

    def moon_illumination(self, t=None):
        """Returns the current illumination of the moon"""

        logger.debug(f"Observatory.moon_illumination({t}) called")

        if t is None:
            t = self.observatory_time
        else:
            t = astrotime.Time(t)

        sun = coord.get_sun(t)
        moon = coord.get_body("moon", t)
        elongation = sun.separation(moon)
        phase_angle = np.arctan2(
            sun.distance * np.sin(elongation),
            moon.distance - sun.distance * np.cos(elongation),
        )
        return (1.0 + np.cos(phase_angle.value)) / 2.0

    # def get_object_altaz(
    #     self, obj=None, ra=None, dec=None, unit=("hr", "deg"), frame="icrs", t=None
    # ):
    #     """Returns the altitude and azimuth of the requested object at the requested time"""

    #     logger.debug(
    #         f"Observatory.get_object_altaz({obj}, {ra}, {dec}, {unit}, {frame}, {t}) called"
    #     )

    #     obj = self._parse_obj_ra_dec(obj, ra, dec, unit, frame)
    #     if t is None:
    #         t = self.observatory_time
    #     t = astrotime.Time(t)

    #     return obj.transform_to(
    #         coord.AltAz(obstime=t, location=self.observatory_location)
    #     )
    def get_object_altaz(
        self, obj=None, ra=None, dec=None, unit=("hr", "deg"), frame="icrs", t=None
    ):
        logger.debug(
            f"Called with obj={obj}, ra={ra}, dec={dec}, unit={unit}, frame={frame}, time={t}"
        )

        if obj is None and (ra is None or dec is None):
            logger.error("Either obj or both ra and dec must be provided.")
            return None

        if obj is None:
            try:
                ra_unit, dec_unit = (u.hourangle if unit[0] == "hr" else u.deg, u.deg)
                obj = SkyCoord(ra=ra, dec=dec, unit=(ra_unit, dec_unit), frame=frame)
            except ValueError as e:
                logger.error(f"Invalid coordinate values or units: {e}")
                return None

        if t is None:
            t = self.observatory_time
        if not isinstance(t, astrotime.Time):
            try:
                t = astrotime.Time(t)
            except ValueError as e:
                logger.error(f"Invalid time value: {e}")
                return None

        altaz_frame = coord.AltAz(obstime=t, location=self.observatory_location)
        try:
            altaz = obj.transform_to(altaz_frame)
        except Exception as e:
            logger.error(f"Error transforming coordinates: {e}")
            return None

        return altaz

    def get_object_slew(
        self, obj=None, ra=None, dec=None, unit=("hr", "deg"), frame="icrs", t=None
    ):
        """Determines the slew coordinates of the requested object at the requested time"""

        logger.debug(
            f"Observatory.get_object_slew({obj}, {ra}, {dec}, {unit}, {frame}, {t}) called"
        )

        obj = self._parse_obj_ra_dec(obj, ra, dec, unit, frame)
        if t is None:
            t = self.observatory_time
        t = astrotime.Time(t)

        eq_system = self.telescope.EquatorialSystem
        # eq_system = 1 # TODO: Remove this line, this is a temp. fix for our SiTech mount
        if eq_system == 0:
            logger.warning(
                "Telescope equatorial system is not set, assuming Topocentric"
            )
            eq_system = 1

        if eq_system == 1:
            logger.debug("Converting object to TETE")
            obj_slew = obj.transform_to(
                coord.TETE(obstime=t, location=self.observatory_location)
            )
        elif eq_system == 2:
            obj_slew = obj.transform_to("icrs")
        elif eq_system == 3:
            logger.info("Astropy does not support J2050 ICRS yet, using FK5")
            obj_slew = obj.transform_to(coord.FK5(equinox="J2050"))
        elif eq_system == 4:
            obj_slew = obj.transform_to(coord.FK4(equinox="B1950"))

        return obj_slew

    def get_current_object(self):
        """Returns the current pointing of the telescope in ICRS"""

        logger.debug("Observatory.get_current_object() called")

        eq_system = self.telescope.EquatorialSystem
        if eq_system in (0, 1):
            obj = self._parse_obj_ra_dec(
                ra=self.telescope.RightAscension,
                dec=self.telescope.Declination,
                frame=coord.TETE(
                    obstime=self.observatory_time, location=self.observatory_location
                ),
            )
        elif eq_system == 2:
            obj = self._parse_obj_ra_dec(
                ra=self.telescope.RightAscension, dec=self.telescope.Declination
            )
        elif eq_system == 3:
            obj = self._parse_obj_ra_dec(
                ra=self.telescope.RightAscension,
                dec=self.telescope.Declination,
                frame=coord.FK5(equinox="J2050"),
            )
        elif eq_system == 4:
            obj = self._parse_obj_ra_dec(
                ra=self.telescope.RightAscension,
                dec=self.telescope.Declination,
                frame=coord.FK4(equinox="B1950"),
            )
        return obj

    def generate_header_dict(self):
        """Generates the header information for the observatory as a dictionary

        Returns
        -------
        dict
            The header information
        """
        hdr_dict = {}
        hdr_dict.update(self.observatory_info)
        hdr_dict.update(self.camera_info)
        hdr_dict.update(self.telescope_info)
        hdr_dict.update(self.cover_calibrator_info)
        hdr_dict.update(self.dome_info)
        hdr_dict.update(self.filter_wheel_info)
        hdr_dict.update(self.focuser_info)
        hdr_dict.update(self.observing_conditions_info)
        hdr_dict.update(self.rotator_info)
        hdr_dict.update(self.safety_monitor_info)
        hdr_dict.update(self.switch_info)
        hdr_dict.update(self.threads_info)
        hdr_dict.update(self.autofocus_info)

        return hdr_dict

    def generate_header_info(
        self,
        filename,
        frametyp=None,
        custom_header=None,
        history=None,
        maxim=False,
        allowed_overwrite=[],
    ):
        """Generates the header information for the observatory"""
        if not maxim:
            hdr = fits.Header()
        else:
            logger.info("Getting header from MaxIm image")
            hdr = fits.getheader(filename)

        hdr["BSCALE"] = (1, "physical=BZERO + BSCALE*array_value")
        hdr["BZERO"] = (32768, "physical=BZERO + BSCALE*array_value")
        if maxim:
            hdr["SWUPDATE"] = ("pyscope", "Software used to update file")
            hdr["SWVERSIO"] = (__version__, "Version of software used to update file")
        else:
            hdr["SWCREATE"] = ("pyscope", "Software used to create file")
            hdr["SWVERSIO"] = (__version__, "Version of software used to create file")
        hdr["ROWORDER"] = ("TOP-DOWN", "Row order of image")

        if frametyp is not None:
            hdr["FRAMETYP"] = (frametyp, "Frame type")
        elif self.last_camera_shutter_status:
            hdr["FRAMETYP"] = ("Light", "Frame type")
        elif not self.last_camera_shutter_status:
            hdr["FRAMETYP"] = ("Dark", "Frame type")

        hdr_dict = self.generate_header_dict()

        if custom_header is not None:
            hdr_dict.update(custom_header)

        self.safe_update_header(
            hdr, hdr_dict, maxim=maxim, allowed_overwrite=allowed_overwrite
        )

        if history is not None:
            if type(history) is str:
                history = [history]
            for hist in history:
                hdr["HISTORY"] = hist

        return hdr

    def safe_update_header(self, hdr, hdr_dict, maxim=False, allowed_overwrite=[]):
        """Safely updates the header information"""
        logger.debug(f"Observatory.safe_update_header called")
        if maxim:
            # Only keep the allowed_overwrite keys in the hdr_dict
            # First get keys in existing header
            existing_keys = hdr.keys()
            # If the key is in the existing header, and not in the allowed_overwrite list, remove it
            for key in existing_keys:
                if key not in allowed_overwrite:
                    hdr_dict.pop(key, None)

        # hdr_dict = {k: v for k, v in hdr_dict.items() if k in allowed_overwrite}

        # convert masked values to None and lists to strings
        for key, value in hdr_dict.items():
            if type(value[0]) == np.ma.core.MaskedConstant:
                hdr_dict[key] = (None, value[1])
            if type(value[0]) == list:
                hdr_dict[key] = (str(value[0]), value[1])

        # remove values = () from the dictionary
        hdr_dict = {k: v for k, v in hdr_dict.items() if v != () and v[0] != ()}

        # remove any keys that are not strings
        hdr_dict = {k: v for k, v in hdr_dict.items() if type(k) is str}

        # remove any keys with a ? in them
        hdr_dict = {k: v for k, v in hdr_dict.items() if "?" not in k}

        # hdr.update(hdr_dict)
        try:
            hdr.update(hdr_dict)
        except Exception as e:
            logger.error(f"Failed to update FITS header: {e}")
            logger.error(f"hdr_dict: {hdr_dict}")

    def save_last_image(
        self,
        filename,
        frametyp=None,
        overwrite=False,
        custom_header=None,
        history=None,
        allowed_overwrite=[],
        # **kwargs,
    ):
        """Saves the current image"""

        logger.debug(
            f"Observatory.save_last_image({filename}, {frametyp}, {overwrite}, {custom_header}, {history}) called"
        )

        if not self.camera.ImageReady:
            logger.exception("Image is not ready, cannot be saved")
            return False

        maxim = self.camera_driver.lower() in ("maxim", "maximdl", "_maximcamera")
        # print(self.camera_driver.lower())

        # If camera driver is Maxim, use Maxim to save the image
        # This is because Maxim does not pass some of the header information
        # to the camera object, so it is not available to be saved.
        if not maxim:
            # Read out the image array
            img_array = self.camera.ImageArray

            if img_array is None or len(img_array) == 0 or len(img_array) == 0:
                logger.exception("Image array is empty, cannot be saved")
                return False
        else:
            # print("Using Maxim to save image")
            logger.info("Using Maxim to save image")
            allowed_overwrite = [
                "AIRMASS",
                "OBJECT",
                "TELESCOP",
                "INSTRUME",
                "OBSERVER",
            ]
            logger.info(f"Overwrite allowed for header keys {allowed_overwrite}")
            self.camera.VerifyLatestExposure()
            # TODO: Below should be updated to the filepath we want to save to
            filepath = os.path.join(os.getcwd(), filename)
            self.camera.SaveImageAsFits(filepath)
            img_array = fits.getdata(filename)
        try:
            hdr = self.generate_header_info(
                filename, frametyp, custom_header, history, maxim, allowed_overwrite
            )
            # update RADECSYS key to RADECSYSa
            if "RADECSYS" in hdr:
                hdr["RADECSYSa"] = hdr["RADECSYS"]
                hdr.pop("RADECSYS", None)
            hdu = fits.PrimaryHDU(img_array, header=hdr)
        except Exception as e:
            logger.exception(f"Error generating header information: {e}")
            hdu = fits.PrimaryHDU(img_array)

        hdu.writeto(filename, overwrite=overwrite)

        return True

    def set_filter_offset_focuser(self, filter_index=None, filter_name=None):
        logger.debug(
            f"Observatory.set_filter_offset_focuser({filter_index}, {filter_name}) called"
        )

        if filter_name is None:
            try:
                filter_name = self.filters[filter_index]
                logger.info("Filter %s found at index %i" % (filter_name, filter_index))
            except:
                raise ObservatoryException(
                    "Filter %s not found in filter list" % filter_name
                )
        elif filter_index is None:
            try:
                filter_index = self.filters.index(filter_name)
                logger.info("Filter %s found at index %i" % (filter_name, filter_index))
            except:
                raise ObservatoryException(
                    "Filter %s not found in filter list" % filter_name
                )

        if self.filter_wheel is not None:
            if self.filter_wheel.Connected:
                logger.info("Setting filter wheel to filter %i" % filter_index)
                self.filter_wheel.Position = filter_index
                logger.info("Filter wheel set")
            else:
                raise ObservatoryException("Filter wheel is not connected.")
        else:
            raise ObservatoryException("There is no filter wheel.")

        if self.focuser is not None:
            if self.focuser.Connected and self.filter_focus_offsets[filter_name] != 0:
                self._current_focus_offset = (
                    self.filter_focus_offsets[filter_name] - self.current_focus_offset
                )
                # TODO: fix this if self.current_focus_offset < self.focuser.MaxIncrement:
                if self.focuser.Absolute:
                    if (
                        self.focuser.Position + self.current_focus_offset
                        > 0
                        # and self.focuser.Position + self.current_focus_offset
                        # < self.focuser.MaxStep
                    ):
                        logger.info(
                            "Focuser moving to position %i"
                            % (self.focuser.Position + self.current_focus_offset)
                        )
                        self.focuser.Move(
                            int(self.focuser.Position + self.current_focus_offset)
                        )
                        while self.focuser.IsMoving:
                            time.sleep(0.1)
                        logger.info("Focuser moved")
                        return True
                    else:
                        raise ObservatoryException(
                            "Focuser cannot move to the requested position."
                        )
                else:
                    logger.info(
                        "Focuser moving to relative position %i"
                        % self.current_focus_offset
                    )
                    self.focuser.Move(int(self.current_focus_offset))
                    while self.focuser.IsMoving:
                        time.sleep(0.1)
                    logger.info("Focuser moved")
                    return True
            elif self.focuser.Connected and self.filter_focus_offsets[filter_name] == 0:
                logger.info("No configured focus offset for filter %s" % filter_name)
                logger.info("Checking if focuser is moving...")
                time.sleep(1)
                if self.focuser.IsMoving:
                    logger.info("Focuser is moving, waiting...")
                    while self.focuser.IsMoving:
                        time.sleep(0.1)
                    logger.info("Focuser stopped.")
                logger.info("Focuser at position %i" % self.focuser.Position)
                return True
            else:
                raise ObservatoryException("Focuser is not connected.")
        else:
            logger.warning("There is no focuser, skipping setting an offset.")

    def slew_to_coordinates(
        self,
        obj=None,
        ra=None,
        dec=None,
        unit=("hr", "deg"),
        frame="icrs",
        control_dome=False,
        control_rotator=False,
        home_first=False,
        wait_for_slew=True,
        track=True,
    ):
        """Slews the telescope to a given ra and dec"""

        logger.debug(
            f"Observatory.slew_to_coordinates({obj}, {ra}, {dec}, {unit}, {frame}, {control_dome}, {control_rotator}, {home_first}, {wait_for_slew}, {track}) called"
        )

        obj = self._parse_obj_ra_dec(obj, ra, dec, unit, frame)

        logger.info(
            "Slewing to RA %s and Dec %s"
            % (
                obj.ra.hms,
                obj.dec.dms,
            )
        )
        slew_obj = self.get_object_slew(obj)
        altaz_obj = self.get_object_altaz(obj)

        if not self.telescope.Connected:
            raise ObservatoryException("The telescope is not connected.")

        # if not isinstance(altaz_obj.alt, u.Quantity):
        #     altaz_obj.alt = altaz_obj.alt * u.deg

        if altaz_obj.alt <= self.min_altitude:
            logger.exception(
                "Target is below the minimum altitude of %.2f degrees"
                % self.min_altitude.to(u.deg).value
            )
            return False

        if self.telescope.Altitude < self.min_altitude.to(u.deg).value:
            logger.exception(
                "Telescope is below the minimum altitude of %.2f degrees"
                % self.min_altitude.to(u.deg).value
            )
            return False

        if control_rotator and self.rotator is not None:
            self.stop_derotation_thread()

        if self.telescope.CanPark:
            if self.telescope.AtPark:
                logger.info("Telescope is parked, unparking...")
                self.telescope.Unpark()
                logger.info("Unparked.")
                if self.telescope.CanFindHome and home_first:
                    logger.info("Finding home position...")
                    self.telescope.FindHome()
                    logger.info("Found home position.")

        if track and self.telescope.CanSetTracking:
            logger.info("Turning on sidereal tracking...")
            # self.telescope.TrackingRate = self.telescope.TrackingRates[0] # ! FIX THIS
            self.telescope.Tracking = True
            logger.info("Sidereal tracking is on.")
        else:
            logger.warning("Tracking cannot be turned on.")

        logger.info("Attempting to slew to coordinates...")
        logger.info(
            "Slewing to RA %.5f and Dec %.5f" % (slew_obj.ra.hour, slew_obj.dec.deg)
        )
        if self.telescope.CanSlew:
            if self.telescope.CanSlewAsync:
                self.telescope.SlewToCoordinatesAsync(
                    slew_obj.ra.hour, slew_obj.dec.deg
                )
            else:
                self.telescope.SlewToCoordinates(slew_obj.ra.hour, slew_obj.dec.deg)
        elif self.telescope.CanSlewAltAz:
            if self.telescope.CanSlewAltAzAsync:
                self.telescope.SlewToAltAzAsync(Altitude = altaz_obj.alt.deg, Azimuth = altaz_obj.az.deg)
            else:
                self.telescope.SlewToAltAz(Altitude = altaz_obj.alt.deg, Azimuth = altaz_obj.az.deg)
        else:
            raise ObservatoryException("The telescope cannot slew to coordinates.")

        if control_dome and self.dome is not None:
            if self.dome.ShutterStatus == "Closed" and self.dome.CanSetShutter:
                if self.dome.CanFindHome:
                    logger.info("Finding the dome home...")
                    self.dome.FindHome()
                    logger.info("Found.")
                logger.info("Opening the dome shutter...")
                self.dome.OpenShutter()
                logger.info("Opened.")
            if self.dome.CanPark:
                if self.dome.AtPark and self.dome.CanFindHome:
                    logger.info("Finding the dome home...")
                    self.dome.FindHome()
                    logger.info("Found.")
            if not self.dome.Slaved:
                if self.dome.CanSetAltitude:
                    logger.info("Setting the dome altitude...")
                    self.dome.SlewToAltitude(altaz_obj.alt.deg)
                    logger.info("Set.")
                if self.dome.CanSetAzimuth:
                    logger.info("Setting the dome azimuth...")
                    logger.info("Set.")
                    self.dome.SlewToAzimuth(altaz_obj.az.deg)

        if control_rotator and self.rotator is not None:
            rotation_angle = (self.lst().value - slew_obj.ra.hourangle) * 15
            if (
                self.rotator.MechanicalPosition + rotation_angle
                >= self.rotator_max_angle
                or self.rotator.MechanicalPosition - rotation_angle
                <= self.rotator_min_angle
            ):
                logger.warning(
                    "Rotator will pass through the limit. Cannot slew to target."
                )
                control_rotator = False

            logger.info("Rotating the rotator to hour angle %.2f" % rotation_angle)
            self.rotator.MoveAbsolute(rotation_angle)
            logger.info("Rotated.")

        condition = wait_for_slew
        while condition:
            condition = self.telescope.Slewing
            if control_dome and self.dome is not None:
                condition = condition or self.dome.Slewing
            if control_rotator and self.rotator is not None:
                condition = condition or self.rotator.IsMoving
            time.sleep(0.1)
        else:
            logger.info("Settling for %.2f seconds..." % self.settle_time)
            time.sleep(self.settle_time)

        return True

    def start_observing_conditions_thread(self, update_interval=60):
        """Starts the observing conditions updating thread"""

        if self.observing_conditions is None:
            raise ObservatoryException("There is no observing conditions object.")

        logger.info("Starting observing conditions thread...")
        self._observing_conditions_event = threading.Event()
        self._observing_conditions_thread = threading.Thread(
            target=self._update_observing_conditions,
            args=(update_interval,),
            daemon=True,
            name="Observing Conditions Thread",
        )
        self._observing_conditions_thread.start()
        logger.info("Observing conditions thread started.")

        return True

    def stop_observing_conditions_thread(self):
        """Stops the observing conditions updating thread"""

        if self._observing_conditions_event is None:
            logger.warning("Observing conditions thread is not running.")
            return False

        logger.info("Stopping observing conditions thread...")
        self._observing_conditions_event.set()
        self._observing_conditions_thread.join()
        self._observing_conditions_event = None
        self._observing_conditions_thread = None
        logger.info("Observing conditions thread stopped.")

        return True

    def _update_observing_conditions(self, wait_time=0):
        """Updates the observing conditions"""
        while not self._observing_conditions_event.is_set():
            logger.debug("Updating observing conditions...")
            self.observing_conditions.Refresh()
            time.sleep(wait_time)

    def start_safety_monitor_thread(self, on_fail=None, update_interval=60):
        """Starts the safety monitor updating thread"""

        if self.safety_monitor is None:
            raise ObservatoryException("Safety monitor is not connected.")

        if on_fail is None:
            logger.info(
                "No safety monitor failure function provided. Using default shutdown function"
            )
            on_fail = self.shutdown

        logger.info("Starting safety monitor thread...")
        self._safety_monitor_event = threading.Event()
        self._safety_monitor_thread = threading.Thread(
            target=self._update_safety_monitor,
            args=(
                on_fail,
                update_interval,
            ),
            daemon=True,
            name="Safety Monitor Thread",
        )
        self._safety_monitor_thread.start()
        logger.info("Safety monitor thread started.")

        return True

    def stop_safety_monitor_thread(self):
        """Stops the safety monitor updating thread"""

        if self._safety_monitor_event is None:
            logger.warning("Safety monitor thread is not running.")
            return False

        logger.info("Stopping safety monitor thread...")
        self._safety_monitor_event.set()
        self._safety_monitor_thread.join()
        self._safety_monitor_event = None
        self._safety_monitor_thread = None
        logger.info("Safety monitor thread stopped.")

        return True

    def _update_safety_monitor(self, on_fail, wait_time=0):
        """Updates the safety monitor"""
        while not self._safety_monitor_event.is_set():
            logger.debug("Updating safety monitor...")
            safety_array = self.safety_status()
            if not all(safety_array):
                logger.warning(
                    'Safety monitor is not safe, calling on_fail function "%s" and ending thread...'
                    % on_fail.__name__
                )
                on_fail()
                self.stop_safety_monitor_thread()
                return
            time.sleep(wait_time)

    def start_derotation_thread(self, update_interval=0.1):
        """Begin a derotation thread for the current ra and dec"""

        if self.rotator is None:
            raise ObservatoryException("There is no rotator object.")

        obj = self.get_current_object().transform_to(
            coord.AltAz(
                obstime=astrotime.Time.now(), location=self.observatory_location
            )
        )

        logger.info("Starting derotation thread...")
        self._derotation_event = threading.Event()
        self._derotation_thread = threading.Thread(
            target=self._update_rotator,
            args=(obj, update_interval),
            daemon=True,
            name="Derotation Thread",
        )
        self._derotation_thread.start()
        logger.info("Derotation thread started.")

        return True

    def stop_derotation_thread(self):
        """Stops the derotation thread"""

        if self._derotation_event is None:
            logger.warning("Derotation thread is not running.")
            return False

        logger.info("Stopping derotation thread...")
        self._derotation_event.set()
        self._derotation_thread.join()
        self._derotation_event = None
        self._derotation_thread = None
        logger.info("Derotation thread stopped.")

        return True

    def _update_rotator(self, obj, wait_time=1):
        """Updates the rotator"""
        # mean sidereal rate (at J2000) in radians per second
        SR = 7.292115855306589e-5
        deg = np.pi / 180

        command = (
            -(np.cos(obj.az.rad) * np.cos(self.latitude.rad) / np.cos(obj.alt.rad))
            * SR
            / deg
            * wait_time
        )

        while not self._derotation_event.is_set():
            self.rotator.Move(command)

            t0 = self.observatory_time
            obj = obj.transform_to(
                coord.AltAz(
                    obstime=t0 + wait_time * u.second,
                    location=self.observatory_location,
                )
            )

            command = (
                -(np.cos(obj.az.rad) * np.cos(self.latitude.rad) / np.cos(obj.alt.rad))
                * SR
                / deg
                * wait_time
            )

            time.sleep(wait_time - (self.observatory_time - t0).sec)

    def safety_status(self):
        """Returns the status of the safety monitors"""

        logger.debug("Observatory.safety_status() called")

        safety_array = []
        if self.safety_monitor is not None:
            for safety_monitor in self.safety_monitor:
                safety_array.append(safety_monitor.IsSafe)
        return safety_array

    def switch_status(self):
        """Returns the status of the switches"""

        logger.debug("Observatory.switch_status() called")

        switch_array = []
        if self.switch is not None:
            for switch in self.switch:
                temp = []
                for i in range(switch.MaxSwitch):
                    temp.append(switch.GetSwitch(i))
                switch_array.append(temp)
        return switch_array

    def run_autofocus(
        self,
        exposure=3,
        midpoint=0,
        nsteps=5,
        step_size=500,
        use_current_pointing=False,
        save_images=False,
        save_path=None,
        binning=2,  # HOTFIX for 6200
    ):
        """Runs the autofocus routine"""

        if self.autofocus is not None:
            logger.info("Using %s to run autofocus..." % self.autofocus_driver)
            result = self.autofocus.Run(exposure=exposure)
            logger.info("Autofocus routine completed.")
            return result
        elif self.focuser is not None:
            logger.info("Using observatory autofocus routine...")

            if not use_current_pointing:
                logger.info("Slewing to zenith...")
                self.slew_to_coordinates(
                    obj=coord.SkyCoord(
                        alt=90 * u.deg,
                        az=0 * u.deg,
                        frame=coord.AltAz(
                            obstime=self.observatory_time,
                            location=self.observatory_location,
                        ),
                    ),
                    control_dome=(self.dome is not None),
                    control_rotator=(self.rotator is not None),
                )
                logger.info("Slewing complete.")

            logger.info("Starting autofocus routine...")

            test_positions = np.linspace(
                midpoint - step_size * (nsteps // 2),
                midpoint + step_size * (nsteps // 2),
                nsteps,
                endpoint=True,
            )
            test_positions = test_positions.astype(int)

            autofocus_time = self.observatory_time.isot.replace(":", "-")

            if save_path is None:
                save_path = Path(
                    os.getcwd(), "images", "autofocus", f"{autofocus_time}"
                ).resolve()

            focus_values = []
            for i, position in enumerate(test_positions):
                logger.info("Moving focuser to %s..." % position)
                if self.focuser.Absolute:
                    self.focuser.Move(int(position))
                    while self.focuser.IsMoving:
                        time.sleep(0.1)
                elif i == 0:
                    self.focuser.Move(-int(position[0]))
                    while self.focuser.IsMoving:
                        time.sleep(0.1)
                else:
                    self.focuser.Move(int(step_size))
                    while self.focuser.IsMoving:
                        time.sleep(0.1)
                logger.info("Focuser moved.")

                # Set binning
                self.camera.BinX = binning

                logger.info("Taking %s second exposure..." % exposure)
                self.camera.StartExposure(exposure, True)
                while not self.camera.ImageReady:
                    time.sleep(0.1)
                logger.info("Exposure complete.")

                logger.info("Calculating mean star fwhm...")
                if not save_images:
                    save_path = Path(
                        tempfile.gettempdir(), f"{autofocus_time}"
                    ).resolve()
                if not save_path.exists():
                    save_path.mkdir(parents=True)
                fname = save_path / f"FOCUS{int(position)}.fit"

                self.save_last_image(fname, frametyp="Focus", overwrite=True)

                # Removed for hotfix for PlateSolve2
                # cat = detect_sources_photutils(
                #     fname,
                #     threshold=100,
                #     deblend=False,
                #     tbl_save_path=Path(str(fname).replace(".fts", ".ecsv")),
                # )
                # focus_values.append(np.mean(cat.fwhm.value))
                # logger.info("FWHM = %.1f pixels" % focus_values[-1])

            # fit hyperbola to focus values

            # Removed for hotfix for PlateSolve2
            # popt, pcov = curve_fit(
            #     lambda x, x0, a, b, c: a / b * np.sqrt(b**2 + (x - x0) ** 2) + c,
            #     test_positions,
            #     focus_values,
            #     p0=[midpoint, 1, 1, 0],
            #     bounds=(
            #         [midpoint - n_steps * step_size, 0, 0, -1e6],
            #         [midpoint + n_steps * step_size, 1e6, 1e6, 1e6],
            #     ),
            # )
            #
            # result = popt[0]
            # result_err = np.sqrt(np.diag(pcov))[0]

            # Run platesolve 2 from cmd line
            platesolve2_path = Path(
                r"C:\Program Files (x86)\PlaneWave Instruments\PlaneWave Interface 4\PlateSolve2\PlateSolve2.exe"
            ).resolve()
            # print(platesolve2_path)
            results_path = Path(save_path / "results.txt").resolve()
            # print(f"Results path: {results_path}")
            image_path = glob.glob(str(save_path / "*.fit"))[0]
            # print(f"Image path: {image_path}")
            logger.info("Running PlateSolve2...")
            procid = os.spawnv(
                os.P_NOWAIT,
                platesolve2_path,
                [f'"{platesolve2_path}" {image_path},{results_path},180'],
            )

            while results_path.exists() == False:
                time.sleep(0.1)
            # Read results
            with open(results_path, "r") as f:
                results = f.read()
            while results == "":
                time.sleep(0.1)
                with open(results_path, "r") as f:
                    results = f.read()

            print(f"Results path: {results_path}")
            print(results)
            results = results.split(",")
            # Remove whitespace
            results = [x.strip() for x in results]
            print(results)
            result, fwhm, result_err = (
                float(results[0]),
                float(results[1]),
                float(results[2]),
            )
            print(f"Best focus: {result}")
            print(f"FWHM: {fwhm}")
            print(f"Focus error: {result_err}")

            logger.info(f"Best focus position is {result} +/- {result_err}")

            if result < test_positions[0] or result > test_positions[-1]:
                logger.warning("Best focus position is outside the test range.")
                logger.warning(
                    "Using the midpoint of the test range as the best focus position."
                )
                result = midpoint

            logger.info("Moving focuser to best focus position...")
            if self.focuser.Absolute:
                self.focuser.Move(int(result))
                while self.focuser.IsMoving:
                    time.sleep(0.1)
            else:
                self.focuser.Move(int(test_positions[-1] - result))
                while self.focuser.IsMoving:
                    time.sleep(0.1)
            logger.info("Focuser moved.")
            logger.info("Autofocus routine complete.")

            return result
        else:
            raise ObservatoryException(
                "There is no focuser or autofocus driver present."
            )

    def dither_mount(
        self,
        radius=1,
        center_pos=None,
        seed=None,
    ):
        """Dithers the telescope randomly within a region of a given radius around a center position.

        Parameters
        ----------
        radius : `float`, optional (default = 1)
            The radius in arcseconds to dither the telescope.

        center_pos : `~astropy.coordinates.SkyCoord`, optional
            The center position to dither around. If None, the current pointing of the mount will be used.

        seed : `int`, optional
            The seed to use for the random number generator. If None, the seed will be randomly generated.

        Returns
        -------
        None
        """

        if center_pos is None:
            center_pos = self.get_current_object()

        random_state = np.random.RandomState(seed)
        random_angle = random_state.uniform(0, 2 * np.pi)
        random_radius = random_state.uniform(0, radius) * u.arcsec

        new_ra = center_pos.ra + random_radius * np.cos(random_angle)
        new_dec = center_pos.dec + random_radius * np.sin(random_angle)
        obj = coord.SkyCoord(ra=new_ra, dec=new_dec, frame=center_pos.frame)
        self.slew_to_coordinates(obj=obj)

    def repositioning(
        self,
        obj=None,
        ra=None,
        dec=None,
        unit=("hr", "deg"),
        frame="icrs",
        target_x_pixel=None,
        target_y_pixel=None,
        initial_offset_dec=0,
        check_and_refine=True,
        max_attempts=5,
        tolerance=3,
        exposure=10,
        readout=0,
        binning=2,  # HOTFIX: HARDCODED FOR ASI6200
        save_images=False,
        save_path="./",
        settle_time=5,
        do_initial_slew=True,
        solver="astrometry_net_wcs",  # or "maxim_pinpoint_wcs"
    ):
        """Attempts to place the requested right ascension and declination at the requested pixel location
        on the detector.

        Parameters
        ----------
        obj : `str` or `~astropy.coordinates.SkyCoord`, optional
            The name of the target or a `~astropy.coordinates.SkyCoord` object of the target. If a string,
            a query will be made to the SIMBAD database to get the coordinates. If a `~astropy.coordinates.SkyCoord`
            object, the coordinates will be used directly. If `None`, the ra and dec parameters must be specified.
        ra : `~astropy.coordinates.Longitude`-like, optional
            The ICRS J2000 right ascension of the target that will initialize a `~astropy.coordinates.SkyCoord`
            object. This will override the ra value in the object parameter.
        dec : `~astropy.coordinates.Latitude`-like, optional
            The ICRS J2000 declination of the target that will initialize a `~astropy.coordinates.SkyCoord`
            object. This will override the dec value in the object parameter.
        unit : `tuple`, optional
            The units of the ra and dec parameters. Default is ('hr', 'deg').
        frame : `str`, optional
            The coordinate frame of the ra and dec parameters. Default is 'icrs'.
        target_x_pixel : `float`, optional
            The desired x pixel location of the target.
        target_y_pixel : `float`, optional
            The desired y pixel location of the target.
        initial_offset_dec : `float`, optional
            The initial offset of declination in arcseconds to use for the slew. Default is 0. Ignored if
            do_initial_slew is `False`.
        check_and_refine : `bool`, optional
            Whether or not to check the offset and refine the slew. Default is True.
        max_attempts : `int`, optional
            The maximum number of attempts to make to center the target. Default is 5. Ignored if
            check_and_refine is False.
        tolerance : `float`, optional
            The tolerance in pixels to consider the target centered. Default is 3. Ignored if
            check_and_refine is `False`.
        exposure : `float`, optional
            The exposure time in seconds to use for the centering images. Default is 10.
        readout : `int`, optional
            The readout mode to use for the centering images. Default is 0.
        save_images : `bool`, optional
            Whether or not to save the centering images. Default is `False`.
        save_path : `str`, optional
            The path to save the centering images to. Default is the current directory. Ignored if
            save_images is `False`.
        settle_time : `float`, optional
            The time in seconds to wait after the slew before checking the offset. Default is 5.
        do_initial_slew : `bool`, optional
            Whether or not to do the initial slew to the target. Default is `True`. If `False`, the current
            telescope position will be used as the starting point for the centering routine.

        Returns
        -------
        success : `bool`
            `True` if the target was successfully centered, `False` otherwise.
        """
        """logger.info(
            f"repositioning called with {obj}, {ra}, {dec}, {unit}, {frame}, {target_x_pixel}, {target_y_pixel}, {initial_offset_dec}, check and refine: {check_and_refine}, {max_attempts}, tol: {tolerance}, {exposure}, {readout}, {save_images}, {save_path}, {sync_mount}, {settle_time}, {do_initial_slew}"
        )"""
        slew_obj = self._parse_obj_ra_dec(obj, ra, dec, unit, frame)

        logger.info(
            "Attempting to put %s on pixel (%.2f, %.2f)"
            % (
                slew_obj.to_string("hmsdms"),
                target_x_pixel,
                target_y_pixel,
            )
        )

        if initial_offset_dec != 0 and do_initial_slew:
            logger.info(
                "Offseting the initial slew declination by %.2f arcseconds"
                % initial_offset_dec
            )

        for attempt in range(max_attempts):
            if check_and_refine:
                logger.info("Attempt %i of %i" % (attempt + 1, max_attempts))

            if attempt == 0:
                # JW EDIT
                if do_initial_slew:
                    ra_hours = coord.Angle(slew_obj.ra.hour, unit=u.hour)
                    dec_degrees = coord.Angle(
                        slew_obj.dec.deg, unit=u.deg
                    ) + coord.Angle(initial_offset_dec, unit=u.arcsec).to(u.deg)
                    self.slew_to_coordinates(
                        ra=ra_hours.hour,
                        dec=dec_degrees.deg,
                        control_dome=(self.dome is not None),
                        control_rotator=(self.rotator is not None),
                    )
                # if do_initial_slew:
                #     self.slew_to_coordinates(
                #         ra=slew_obj.ra.hour,
                #         dec=slew_obj.dec.deg + initial_offset_dec / 3600,
                #         control_dome=(self.dome is not None),
                #         control_rotator=(self.rotator is not None),
                #     )
            else:
                self.slew_to_coordinates(
                    ra=slew_obj.ra.hour,
                    dec=slew_obj.dec.deg,
                    control_dome=(self.dome is not None),
                    control_rotator=(self.rotator is not None),
                )

            logger.info("Settling for %.2f seconds" % self.settle_time)
            time.sleep(self.settle_time)

            if not check_and_refine and attempt > 0:
                logger.info(
                    "Check and repositioning is off, single-shot repositioning complete"
                )
                return True

            logger.info("Taking %.2f second exposure" % exposure)
            self.camera.ReadoutMode = readout
            self.camera.BinX = binning
            self.camera.StartExposure(exposure, True)
            while not self.camera.ImageReady:
                time.sleep(0.1)
            logger.info("Exposure complete")

            temp_image = Path(
                tempfile.gettempdir()
                + "%s.fts"
                % astrotime.Time(self.observatory_time, format="fits").value.replace(
                    ":", "-"
                )
            )
            self.save_last_image(temp_image, overwrite=True)

            logger.info("Searching for a WCS solution")
            logger.info(
                "Pixel scale is %.2f arcseconds per pixel" % self.pixel_scale[0]
            )
            if solver.lower() == "astrometry_net_wcs":
                from ..reduction import astrometry_net_wcs

                solution_found = astrometry_net_wcs(
                    temp_image,
                    # center_ra=slew_obj.ra.deg,
                    # center_dec=slew_obj.dec.deg,
                    # radius=1.0,
                    # scale_units="arcsecperpix",
                    # scale_type="ev",
                    # scale_est=self.pixel_scale[0],
                    # scale_err=self.pixel_scale[0] * 0.2,
                    # parity=2,
                    # tweak_order=3,
                    # crpix_center=True,
                    # solve_timeout=300,
                )
            elif solver.lower() == "maxim_pinpoint_wcs":
                from ..reduction import maxim_pinpoint_wcs

                solution_found = maxim_pinpoint_wcs(temp_image)
            else:
                logger.warning("Unknown WCS solver, skipping this attempt")
                continue

            if save_images:
                save_name = str(Path(save_path) / temp_image.name)
                logger.info("Saving the centering image to %s" % save_name)
                self.save_last_image(
                    save_name,
                    overwrite=True,
                )

            if not solution_found:
                logger.warning("No WCS solution found, skipping this attempt")
                continue

            logger.info(
                "WCS solution found, solving for the pixel location of the target"
            )
            try:
                hdr = fits.getheader(temp_image)
                w = astropywcs.WCS(hdr)

                center_coord = w.pixel_to_world(
                    int(self.camera.CameraXSize / 2), int(self.camera.CameraYSize / 2)
                )
                logger.debug(
                    "Center of the image is at %s" % center_coord.to_string("hmsdms")
                )

                target_coord = w.pixel_to_world(target_x_pixel, target_y_pixel)
                target_pixel_ra = target_coord.ra.hour
                target_pixel_dec = target_coord.dec.deg
                logger.debug("Target is at %s" % target_coord.to_string("hmsdms"))

                pixels = w.world_to_pixel(obj)
                obj_x_pixel = pixels[0]
                obj_y_pixel = pixels[1]
                logger.debug(
                    "Object is at pixel (%.2f, %.2f)" % (obj_x_pixel, obj_y_pixel)
                )
            except Exception as e:
                logger.warning(e)
                logger.warning(
                    "Could not solve for the pixel location of the target, skipping this attempt"
                )
                continue

            error_ra = obj.ra.hour - target_pixel_ra
            error_dec = obj.dec.deg - target_pixel_dec
            error_x_pixels = obj_x_pixel - target_x_pixel
            error_y_pixels = obj_y_pixel - target_y_pixel
            logger.info("Error in RA is %.2f arcseconds" % (error_ra * 15 * 3600))
            logger.info("Error in Dec is %.2f arcseconds" % (error_dec * 3600))
            logger.info("Error in x pixels is %.2f" % error_x_pixels)
            logger.info("Error in y pixels is %.2f" % error_y_pixels)

            if np.sqrt(error_x_pixels**2 + error_y_pixels**2) <= tolerance:
                break

            logger.info("Offsetting next slew coordinates")

            slew_obj = coord.SkyCoord(
                ra=slew_obj.ra.hour + error_ra,
                dec=slew_obj.dec.deg + error_dec,
                unit=("hour", "deg"),
                frame=slew_obj.frame,
            )
            logger.info(slew_obj)
        else:
            logger.warning(
                "Target could not be centered after %d attempts" % max_attempts
            )
            return False

        logger.info("Target is now in position after %d attempts" % (attempt + 1))

        return True

    def take_flats(
        self,
        filters,
        filter_exposures,
        filter_brightness=None,
        target_counts=None,
        gain=None,
        readouts=[None],
        binnings=[None],
        repeat=1,
        save_path="./",
        home_telescope=False,
        check_cooler=True,
        tracking=True,
        dither_radius=0,  # arcseconds
        final_telescope_position="no change",
    ):
        """Takes a sequence of flat frames"""

        logger.info("Taking flat frames")

        if self.filter_wheel is None:
            logger.warning("Filter wheel is not available, exiting")
            return False

        if len(filter_exposures) != len(filters):
            logger.warn(
                "Number of filter exposures does not match the number of filters, exiting"
            )
            logger.warning(
                "Expected %i, got %i" % (len(filters), len(filter_exposures))
            )
            logger.warning("Filters: %s" % filters)
            logger.warning("Exposures: %s" % filter_exposures)
            logger.warning("Exiting")
            logger.warning(
                "Note: filters that should be skipped should have an exposure time of 0"
            )
            return False

        save_path = Path(save_path)

        if home_telescope and self.telescope.CanFindHome:
            logger.info("Homing the telescope")
            self.telescope.FindHome()
            logger.info("Homing complete")

        logger.info("Slewing to point at cover calibrator or specified sky location")

        logger.info("Turning off tracking for slew")
        if self.telescope.CanSetTracking:
            self.telescope.Tracking = False
        logger.info("Tracking off")

        if self.telescope.CanSlewAltAzAsync:
            self.telescope.SlewToAltAzAsync(
                Azimuth = self.cover_calibrator_az, Altitude = self.cover_calibrator_alt
            )
        elif self.telescope.CanSlewAltAz:
            self.telescope.SlewToAltAz(
                Azimuth = self.cover_calibrator_az, Altitude = self.cover_calibrator_alt
            )
        elif self.telescope.CanSlew:
            obj = self.get_object_slew(
                obj=coord.AltAz(
                    alt=self.cover_calibrator_alt * u.deg,
                    az=self.cover_calibrator_az * u.deg,
                    obstime=self.observatory_time,
                    location=self.observatory_location,
                )
            )
            self.telescope.SlewToCoordinates(obj.ra.hour, obj.dec.deg)
        while self.telescope.Slewing:
            time.sleep(0.1)
        logger.info("Slew complete")

        dither_center = self.get_current_object()

        if tracking:
            logger.info("Turning on tracking")
            if self.telescope.CanSetTracking:
                self.telescope.Tracking = True
            logger.info("Tracking on")
        else:
            logger.info("Turning off tracking")
            if self.telescope.CanSetTracking:
                self.telescope.Tracking = False
            logger.info("Tracking off")

        """if self.cover_calibrator is not None:
            if self.cover_calibrator.CoverState != "NotPresent":
                logger.info("Opening the cover calibrator")
                self.cover_calibrator.OpenCover()
                logger.info("Cover open")"""

        if gain is not None:
            logger.info("Setting the camera gain to %i" % gain)
            self.camera.Gain = gain
            logger.info("Camera gain set")

        for filt, filt_exp, idx in zip(filters, filter_exposures, range(len(filters))):

            # skip filters with 0 exposure time
            if filt_exp == 0:
                continue

            # set filter wheel position
            logger.info("Setting the filter wheel to %s" % filt)
            self.filter_wheel.Position = self.filters.index(filt)
            while self.filter_wheel.Position != self.filters.index(filt):
                time.sleep(0.1)
            logger.info("Filter wheel in position")

            # set cover calibrator brightness
            if self.cover_calibrator is not None:
                if type(filter_brightness) is list:
                    logger.info(
                        "Setting the cover calibrator brightness to %i"
                        % filter_brightness[idx]
                    )
                    self.cover_calibrator.CalibratorOn(filter_brightness[idx])
                    logger.info("Cover calibrator on")
            else:
                logger.warning("Cover calibrator not available, assuming sky flats")

            # loop through options
            for readout in readouts:
                if readout is not None:
                    self.camera.ReadoutMode = readout
                for binning in binnings:
                    if binning is not None:
                        self.camera.BinX = binning.split("x")[0]
                        self.camera.BinY = binning.split("x")[1]

                    iter_save_path = save_path / (
                        f"flats_{filt}_{self.camera.BinX}x{self.camera.BinY}_Readout{self.camera.ReadoutMode}"
                        + f"_{filt_exp}s"
                    ).replace(".", "p").replace(" ", "")
                    if not iter_save_path.exists():
                        iter_save_path.mkdir()

                    real_exp = filt_exp
                    for j in tqdm.tqdm(range(repeat)):
                        if (
                            self.camera.CanSetCCDTemperature
                            and self.cooler_setpoint is not None
                            and check_cooler
                        ):
                            while self.camera.CCDTemperature > (
                                self.cooler_setpoint + self.cooler_tolerance
                            ):
                                logger.warning(
                                    "Cooler is not at setpoint, waiting 10 seconds..."
                                )
                                time.sleep(10)
                        if self.filter_wheel.Position != self.filters.index(filt):
                            logger.info("Setting the filter wheel to %s" % filt)
                            self.filter_wheel.Position = self.filters.index(filt)
                            while self.filter_wheel.Position != self.filters.index(
                                filt
                            ):
                                time.sleep(0.1)
                            logger.info("Filter wheel in position")

                        if dither_radius > 0:
                            logger.info("Dithering by %i arcseconds" % dither_radius)
                            self.dither_mount(
                                dither_radius,
                                center_pos=dither_center,
                            )

                        logger.info("Starting %s exposure" % real_exp)
                        self.camera.StartExposure(real_exp, True)

                        iter_save_name = iter_save_path / (
                            f"flat_{filt}_{self.camera.BinX}x{self.camera.BinY}_Readout{self.camera.ReadoutMode}"
                            + f"_{real_exp}s"
                        ).replace(".", "p").replace(" ", "")
                        if type(filter_brightness) is list:
                            iter_save_name = Path(
                                (
                                    str(iter_save_name)
                                    + (f"_Bright{filter_brightness[idx]}" + f"_{j}.fts")
                                )
                            )
                        else:
                            iter_save_name = Path((str(iter_save_name) + f"_{j}.fts"))
                        while not self.camera.ImageReady:
                            time.sleep(1)

                        self.save_last_image(
                            iter_save_name, frametyp="Flat", overwrite=True
                        )
                        logger.info("Flat %i of %i complete" % (j + 1, repeat))
                        logger.info("Saved flat frame to %s" % iter_save_name)

                        if target_counts is not None:
                            logger.info(
                                "Adjusting exposure time to match mean counts to target"
                            )

                            # get the mean counts
                            mean_counts = np.mean(self.camera.ImageArray)
                            logger.info("Mean counts: %i" % mean_counts)

                            # calculate the new exposure time
                            m_ratio = target_counts / mean_counts
                            logger.info(
                                "Ratio of desired brightness to mean counts: %.2f"
                                % m_ratio
                            )
                            real_exp = real_exp * m_ratio
                            logger.info("New exposure time: %.2f" % real_exp)
                        else:
                            real_exp = filt_exp

        if self.cover_calibrator is not None:
            if (
                self.cover_calibrator.CalibratorState is not None
                and self.cover_calibrator.CalibratorState != "NotPresent"
            ):
                logger.info("Turning off the cover calibrator")
                self.cover_calibrator.CalibratorOff()
                logger.info("Cover calibrator off")

            if (
                self.cover_calibrator.CoverState is not None
                and self.cover_calibrator.CalibratorState != "NotPresent"
            ):
                logger.info("Closing the cover calibrator")
                self.cover_calibrator.CloseCover()
                logger.info("Cover closed")

                if final_telescope_position == "no change":
                    logger.info("No change to telescope position requested, exiting")
                elif final_telescope_position == "home" and self.telescope.CanFindHome:
                    logger.info("Homing the telescope")
                    self.telescope.FindHome()
                    logger.info("Homing complete")
                elif final_telescope_position == "park" and self.telescope.CanPark:
                    logger.info("Parking the telescope")
                    self.telescope.Park()
                    logger.info("Parking complete")
        else:
            logger.info(
                "Cover calibrator is None in config file, are you doing sky flats?"
            )

        logger.info("Flats complete")

        return True

    def take_darks(
        self,
        exposures=[1],
        gain=None,
        readouts=[None],
        binnings=[None],
        repeat=1,
        save_path="./",
        frametyp="Dark",
    ):
        """Takes a sequence of dark frames"""

        save_path = Path(save_path)

        logger.info("Taking dark frames")

        if gain is not None:
            logger.info("Setting the camera gain to %i" % gain)
            self.camera.Gain = gain
            logger.info("Camera gain set")

        for exposure in exposures:
            for readout in readouts:
                if readout is not None:
                    self.camera.ReadoutMode = readout
                for binning in binnings:
                    if binning is not None:
                        self.camera.BinX = binning.split("x")[0]
                        self.camera.BinY = binning.split("x")[1]
                    iter_save_path = save_path / (
                        f"darks_{self.camera.BinX}x{self.camera.BinY}_Readout{self.camera.ReadoutMode}"
                        + f"_{exposure}s"
                    ).replace(".", "p").replace(" ", "")
                    if exposure == 0:
                        iter_save_path = save_path / (
                            f"biases_{self.camera.BinX}x{self.camera.BinY}_Readout{self.camera.ReadoutMode}"
                            + f"_{exposure}s"
                        ).replace(".", "p").replace(" ", "")
                    if not iter_save_path.exists():
                        iter_save_path.mkdir()
                    for j in tqdm.tqdm(range(repeat)):
                        if (
                            self.camera.CanSetCCDTemperature
                            and self.cooler_setpoint is not None
                        ):
                            while self.camera.CCDTemperature > (
                                self.cooler_setpoint + self.cooler_tolerance
                            ):
                                logger.warning(
                                    "Cooler is not at setpoint, waiting 10 seconds..."
                                )
                                time.sleep(10)
                        logger.info("Starting %4.4gs dark exposure" % exposure)
                        self.camera.StartExposure(exposure, False)
                        iter_save_name = iter_save_path / (
                            (
                                f"dark_{self.camera.BinX}x{self.camera.BinY}_Readout{self.camera.ReadoutMode}"
                                + f"_{exposure}s_{j}"
                            )
                            .replace(".", "p")
                            .replace(" ", "")
                            + ".fts"
                        )
                        if exposure == 0:
                            iter_save_name = iter_save_path / (
                                (
                                    f"bias_{self.camera.BinX}x{self.camera.BinY}_Readout{self.camera.ReadoutMode}"
                                    + f"_{exposure}s_{j}"
                                )
                                .replace(".", "p")
                                .replace(" ", "")
                                + ".fts"
                            )
                        while not self.camera.ImageReady:
                            time.sleep(0.1)
                        self.save_last_image(
                            iter_save_name, frametyp=frametyp, overwrite=True
                        )
                        logger.info("%i of %i complete" % (j, repeat))
                        logger.info("Saved dark frame to %s" % iter_save_name)

        logger.info("Darks complete")

        return True

    def save_config(self, filename, overwrite=False):
        logger.debug("Saving observatory configuration to %s" % filename)
        if os.path.exists(filename) and not overwrite:
            raise ObservatoryException(
                "The file %s already exists and overwrite is False" % filename
            )
        with open(filename, "w") as configfile:
            self._config.write(configfile)

    def _parse_obj_ra_dec(
        self, obj=None, ra=None, dec=None, unit=("hour", "deg"), frame="icrs", t=None
    ):
        logger.debug(
            f"""Observatory._parse_obj_ra_dec({obj}, {ra}, {dec}, {unit}, {frame}, {t}) called"""
        )

        if type(obj) is str:
            try:
                obj = coord.SkyCoord.from_name(obj)
            except:
                try:
                    if t is None:
                        t = self.observatory_time
                    else:
                        t = astrotime.Time(t)
                    eph = MPC.get_ephemeris(
                        obj,
                        start=t,
                        location=self.observatory_location,
                        number=1,
                        proper_motion="sky",
                    )
                    obj = coord.SkyCoord(
                        ra=eph["RA"],
                        dec=eph["Dec"],
                        unit=("deg", "deg"),
                        pm_ra_cosdec=eph["dRA cos(Dec)"],
                        pm_dec=eph["dDec"],
                        frame="icrs",
                    )
                except:
                    try:
                        obj = coord.get_body(obj, t, self.observatory_location)
                    except:
                        raise ObservatoryException(
                            "The requested object could not be found using "
                            + "Sesame resolver, the Minor Planet Center Query, or the astropy.coordinates get_body function."
                        )
        elif type(obj) is coord.SkyCoord:
            pass
        elif ra is not None and dec is not None:
            obj = coord.SkyCoord(ra=ra, dec=dec, unit=unit, frame=frame)
        else:
            raise Exception("Either the object, the ra, or the dec must be specified.")
        return obj.transform_to("icrs")

    def _read_out_kwargs(self, dictionary):
        logger.debug("Observatory._read_out_kwargs() called")
        self.site_name = dictionary.get("site_name", self.site_name)
        self.instrument_name = dictionary.get("instrument_name", self.instrument_name)
        self.instrument_description = dictionary.get(
            "instrument_description", self.instrument_description
        )
        self.latitude = dictionary.get("latitude", self.latitude)
        self.longitude = dictionary.get("longitude", self.longitude)
        self.elevation = dictionary.get("elevation", self.elevation)
        self.diameter = dictionary.get("diameter", self.diameter)
        self.focal_length = dictionary.get("focal_length", self.focal_length)
        self.max_dimension = dictionary.get("max_dimension", self.max_dimension)
        self.cover_calibrator_alt = dictionary.get(
            "cover_calibrator_alt", self.cover_calibrator_alt
        )
        self.cover_calibrator_az = dictionary.get(
            "cover_calibrator_az", self.cover_calibrator_az
        )
        self.filters = dictionary.get("filters", self.filters)
        self.filter_focus_offsets = dictionary.get(
            "filter_focus_offsets", self.filter_focus_offsets
        )
        self.min_altitude = dictionary.get("min_altitude", self.min_altitude)
        self.settle_time = dictionary.get("settle_time", self.settle_time)
        self.slew_rate = dictionary.get("slew_rate", self.slew_rate)

        self.cooler_setpoint = float(
            dictionary.get("cooler_setpoint", self.cooler_setpoint)
        )
        self.cooler_tolerance = float(
            dictionary.get("cooler_tolerance", self.cooler_tolerance)
        )

        # Not sure if this if statement is a good idea here...
        if dictionary.get("rotator_driver", self.rotator_driver) is not None:
            self.rotator_reverse = dictionary.get(
                "rotator_reverse", self.rotator_reverse
            )
            self.rotator_min_angle = dictionary.get(
                "rotator_min_angle", self.rotator_min_angle
            )
            self.rotator_max_angle = dictionary.get(
                "rotator_max_angle", self.rotator_max_angle
            )

        t = dictionary.get(
            "instrument_reconfig_times",
            self.instrument_reconfig_times,
        )
        self.instrument_reconfig_times = (
            json.loads(t)
            if t is not None and t != "" and t != '"{}"' and t != "{}"
            else None
        )

    @property
    def autofocus_info(self):
        logger.debug("Observatory.autofocus_info() called")
        info = {"AUTODRIV": (self.autofocus_driver, "Autofocus driver")}
        return info

    @property
    def camera_info(self):
        logger.debug("Observatory.camera_info() called")
        try:
            self.camera.Connected = True
        except:
            return {"CONNECT": (False, "Camera connection")}
        info = {
            "CAMCON": (True, "Camera connection"),
            "CAMREADY": (self.camera.ImageReady, "Image ready"),
            "CAMSTATE": (
                self.camera.CameraState,
                "Camera state",
            ),
            "PCNTCOMP": (None, "Function percent completed"),
            "DATE-OBS": (None, "YYYY-MM-DDThh:mm:ss observation start [UT]"),
            "JD": (None, "Julian date"),
            "MJD": (None, "Modified Julian date"),
            "MJD-OBS": (None, "Modified Julian date"),
            "CAMTIME": (None, "Exposure time from camera (T) or user (F)"),
            "EXPTIME": (None, "Exposure time [seconds]"),
            "EXPOSURE": (None, "Exposure time [seconds]"),
            "SUBEXP": (None, "Subexposure time [seconds]"),
            "XBINNING": (self.camera.BinX, "Image binning factor in width"),
            "YBINNING": (self.camera.BinY, "Image binning factor in height"),
            "XORGSUBF": (self.camera.StartX, "Subframe X position"),
            "YORGSUBF": (self.camera.StartY, "Subframe Y position"),
            "XPOSSUBF": (self.camera.NumX, "Subframe X dimension"),
            "YPOSSUBF": (self.camera.NumY, "Subframe Y dimension"),
            "READOUT": (None, "Image readout mode"),
            "READOUTM": (None, "Image readout mode"),
            "FASTREAD": (None, "Fast readout mode"),
            "GAIN": (None, "Electronic gain"),
            "OFFSET": (None, "Image offset"),
            "PULSGUID": (None, "Pulse guiding"),
            "SENSTYP": (None, "Sensor type"),
            "BAYERPAT": (None, "Bayer color pattern"),
            "BAYOFFX": (None, "Bayer X offset"),
            "BAYOFFY": (None, "Bayer Y offset"),
            "HSINKT": (None, "Heat sink temperature [C]"),
            "COOLERON": (None, "Whether the cooler is on"),
            "COOLPOWR": (None, "Cooler power in percent"),
            "SET-TEMP": (None, "Camera temperature setpoint [C]"),
            "CCD-TEMP": (None, "Camera temperature [C]"),
            "CMOS-TMP": (None, "Camera temperature [C]"),
            "CAMNAME": (self.camera.Name, "Name of camera"),
            "CAMERA": (self.camera.Name, "Name of camera"),
            "CAMDRVER": (self.camera.DriverVersion, "Camera driver version"),
            "CAMDRV": (self.camera.DriverInfo[0], "Camera driver info"),
            "CAMINTF": (None, "Camera interface version"),
            "CAMDESC": (self.camera.Description, "Camera description"),
            "SENSOR": (None, "Name of sensor"),
            "WIDTH": (self.camera.CameraXSize, "Width of sensor in pixels"),
            "HEIGHT": (self.camera.CameraYSize, "Height of sensor in pixels"),
            "XPIXSIZE": (self.camera.PixelSizeX, "Pixel width in microns"),
            "YPIXSIZE": (self.camera.PixelSizeY, "Pixel height in microns"),
            "MECHSHTR": (
                self.camera.HasShutter,
                "Whether a camera mechanical shutter is present",
            ),
            "ISSHUTTR": (
                self.camera.HasShutter,
                "Whether a camera mechanical shutter is present",
            ),
            "MINEXP": (None, "Minimum exposure time [seconds]"),
            "MAXEXP": (None, "Maximum exposure time [seconds]"),
            "EXPRESL": (
                None,
                "Exposure time resolution [seconds]",
            ),
            "MAXBINSX": (self.camera.MaxBinX, "Maximum binning factor in width"),
            "MAXBINSY": (self.camera.MaxBinY, "Maximum binning factor in height"),
            "CANASBIN": (self.camera.CanAsymmetricBin, "Can asymmetric bin"),
            "CANABRT": (self.camera.CanAbortExposure, "Can abort exposures"),
            "CANSTP": (self.camera.CanStopExposure, "Can stop exposures"),
            "CANCOOLP": (self.camera.CanGetCoolerPower, "Can get cooler power"),
            "CANSETTE": (
                self.camera.CanSetCCDTemperature,
                "Can camera set temperature",
            ),
            "CANPULSE": (self.camera.CanPulseGuide, "Can camera pulse guide"),
            "FULLWELL": (None, "Full well capacity [e-]"),
            "MAXADU": (None, "Camera maximum ADU value possible"),
            "E-ADU": (None, "Gain [e- per ADU]"),
            "EGAIN": (None, "Electronic gain"),
            "CANFASTR": (None, "Can camera fast readout"),
            "READMDS": (None, "Possible readout modes"),
            "GAINS": (None, "Possible electronic gains"),
            "GAINMIN": (None, "Minimum possible electronic gain"),
            "GAINMAX": (None, "Maximum possible electronic gain"),
            "OFFSETS": (None, "Possible offsets"),
            "OFFSETMN": (None, "Minimum possible offset"),
            "OFFSETMX": (None, "Maximum possible offset"),
            "CAMSUPAC": (None, "Camera supported actions"),
        }
        try:
            info["PCNTCOMP"] = (self.camera.PercentCompleted, info["PCNTCOMP"][1])
        except:
            pass
        try:
            info["DATE-OBS"] = (self.camera.LastExposureStartTime, info["DATE-OBS"][1])
            info["JD"] = (
                astrotime.Time(self.camera.LastExposureStartTime).jd,
                info["JD"][1],
            )
            info["MJD"] = (
                astrotime.Time(self.camera.LastExposureStartTime).mjd,
                info["MJD"][1],
            )
            info["MJD-OBS"] = (
                astrotime.Time(self.camera.LastExposureStartTime).mjd,
                info["MJD-OBS"][1],
            )
        except:
            pass
        try:
            last_exposure_duration = self.camera.LastExposureDuration
            info["EXPTIME"] = (last_exposure_duration, info["EXPTIME"][1])
            info["EXPOSURE"] = (last_exposure_duration, info["EXPOSURE"][1])
        except:
            logger.debug("Could not get last exposure duration")
            pass
        try:
            info["CAMTIME"] = (self.camera.CameraTime, info["CAMTIME"][1])
        except:
            pass
        try:
            info["SUBEXP"] = (self.camera.SubExposureDuration, info["SUBEXP"][1])
        except:
            pass
        info["CANFASTR"] = (self.camera.CanFastReadout, info["CANFASTR"][1])
        if self.camera.CanFastReadout:
            info["READOUT"] = (
                self.camera.ReadoutModes[self.camera.ReadoutMode],
                info["READOUT"][1],
            )
            info["READOUTM"] = (
                self.camera.ReadoutModes[self.camera.ReadoutMode],
                info["READOUTM"][1],
            )
            info["FASTREAD"] = (self.camera.FastReadout, info["FASTREAD"][1])
            info["READMDS"] = (self.camera.ReadoutModes, info["READMDS"][1])
            info["SENSTYP"] = (
                [
                    "Monochrome, Color, \
                RGGB, CMYG, CMYG2, LRGB"
                ][self.camera.SensorType],
                info["SENSTYP"][1],
            )
            if not self.camera.SensorType in (0, 1):
                info["BAYERPAT"] = (self.camera.SensorType, info["BAYERPAT"][1])
                info["BAYOFFX"] = (self.camera.BayerOffsetX, info["BAYOFFX"][1])
                info["BAYOFFY"] = (self.camera.BayerOffsetY, info["BAYOFFY"][1])
        try:
            info["HSINKT"] = (self.camera.HeatSinkTemperature, info["HSINKT"][1])
        except:
            pass
        try:
            info["GAINS"] = (self.camera.Gains, info["GAINS"][1])
            info["GAIN"] = (self.camera.Gains[self.camera.Gain], info["GAIN"][1])
        except:
            try:
                info["GAINMIN"] = (self.camera.GainMin, info["GAINMIN"][1])
                info["GAINMAX"] = (self.camera.GainMax, info["GAINMAX"][1])
                info["GAIN"] = (self.camera.Gain, info["GAIN"][1])
            except:
                pass
        try:
            info["OFFSETS"] = (self.camera.Offsets, info["OFFSETS"][1])
            info["OFFSET"] = (
                self.camera.Offsets[self.camera.Offset],
                info["OFFSET"][1],
            )
        except:
            try:
                info["OFFSETMN"] = (self.camera.OffsetMin, info["OFFSETMN"][1])
                info["OFFSETMX"] = (self.camera.OffsetMax, info["OFFSETMX"][1])
                info["OFFSET"] = (self.camera.Offset, info["OFFSET"][1])
            except:
                pass
        info["CANPULSE"] = (self.camera.CanPulseGuide, info["CANPULSE"][1])
        if self.camera.CanPulseGuide:
            info["PULSGUID"] = (self.camera.IsPulseGuiding, info["PULSGUID"][1])
        try:
            info["COOLERON"] = (self.camera.CoolerOn, info["COOLERON"][1])
        except:
            pass
        info["CANCOOLP"] = (self.camera.CanGetCoolerPower, info["CANCOOLP"][1])
        if self.camera.CanGetCoolerPower:
            info["COOLPOWR"] = (self.camera.CoolerPower, info["COOLPOWR"][1])
        info["CANSETTE"] = (self.camera.CanSetCCDTemperature, info["CANSETTE"][1])
        if self.camera.CanSetCCDTemperature:
            info["SET-TEMP"] = (self.camera.SetCCDTemperature, info["SET-TEMP"][1])
        try:
            info["CCD-TEMP"] = (self.camera.CCDTemperature, info["CCD-TEMP"][1])
            info["CMOS-TMP"] = (self.camera.CMOSTemperature, info["CMOS-TMP"][1])
        except:
            pass
        try:
            info["CANINTF"] = (self.camera.InterfaceVersion, info["CANINTF"][1])
        except:
            pass
        try:
            info["SENSOR"] = (self.camera.SensorName, info["SENSOR"][1])
        except:
            pass
        try:
            info["MINEXP"] = (self.camera.ExposureMin, info["MINEXP"][1])
            info["MAXEXP"] = (self.camera.ExposureMax, info["MAXEXP"][1])
        except:
            pass
        try:
            info["EXPRESL"] = (self.camera.ExposureResolution, info["EXPRESL"][1])
        except:
            pass
        try:
            info["FULLWELL"] = (self.camera.FullWellCapacity, info["FULLWELL"][1])
        except:
            pass
        try:
            info["MAXADU"] = (self.camera.MaxADU, info["MAXADU"][1])
        except:
            pass
        try:
            info["E-ADU"] = (self.camera.ElectronsPerADU, info["E-ADU"][1])
        except:
            pass
        try:
            info["EGAIN"] = (self.camera.Gain, info["EGAIN"][1])
        except:
            pass
        try:
            info["CANFASTR"] = (self.camera.CanFastReadout, info["CANFASTR"][1])
        except:
            pass
        try:
            info["CAMSUPAC"] = (str(self.camera.SupportedActions), info["CAMSUPAC"][1])
        except:
            pass

        return info

    @property
    def cover_calibrator_info(self):
        logger.debug("Observatory.cover_calibrator_info() called")
        if self.cover_calibrator is not None:
            try:
                self.cover_calibrator.Connected = True
            except:
                return {"CCALCONN": (False, "Cover calibrator connected")}
            info = {
                "CCALCONN": (True, "Cover calibrator connected"),
                "CALSTATE": (self.cover_calibrator.CalibratorState, "Calibrator state"),
                "COVSTATE": (self.cover_calibrator.CoverState, "Cover state"),
                "BRIGHT": (None, "Brightness of cover calibrator"),
                # "CCNAME": (self.cover_calibrator.Name, "Cover calibrator name"),
                # "COVCAL": (self.cover_calibrator.Name, "Cover calibrator name"),
                # "CCDRVER": (
                #     self.cover_calibrator.DriverVersion,
                #     "Cover calibrator driver version",
                # ),
                # "CCDRV": (
                #     str(self.cover_calibrator.DriverInfo),
                #     "Cover calibrator driver info",
                # ),
                # "CCINTF": (
                #     self.cover_calibrator.InterfaceVersion,
                #     "Cover calibrator interface version",
                # ),
                # "CCDESC": (
                #     self.cover_calibrator.Description,
                #     "Cover calibrator description",
                # ),
                # "MAXBRITE": (
                #     self.cover_calibrator.MaxBrightness,
                #     "Cover calibrator maximum possible brightness",
                # ),
                # "CCSUPAC": (
                #     str(self.cover_calibrator.SupportedActions),
                #     "Cover calibrator supported actions",
                # ),
            }
            try:
                info["BRIGHT"] = (self.cover_calibrator.Brightness, info["BRIGHT"][1])
            except:
                pass
            return info
        else:
            return {"CCALCONN": (False, "Cover calibrator connected")}

    @property
    def dome_info(self):
        logger.debug("Observatory.dome_info() called")
        if self.dome is not None:
            try:
                self.dome.Connected = True
            except:
                return {"DOMECONN": (False, "Dome connected")}
            info = {
                "DOMECONN": (True, "Dome connected"),
                "DOMEALT": (None, "Dome altitude [deg]"),
                "DOMEAZ": (None, "Dome azimuth [deg]"),
                "DOMESHUT": (None, "Dome shutter status"),
                "DOMESLEW": (self.dome.Slewing, "Dome slew status"),
                "DOMESLAV": (None, "Dome slave status"),
                "DOMEHOME": (None, "Dome home status"),
                "DOMEPARK": (None, "Dome park status"),
                "DOMENAME": (self.dome.Name, "Dome name"),
                "DOMDRVER": (self.dome.DriverVersion, "Dome driver version"),
                "DOMEDRV": (str(self.dome.DriverInfo), "Dome driver info"),
                "DOMEINTF": (self.dome.InterfaceVersion, "Dome interface version"),
                "DOMEDESC": (self.dome.Description, "Dome description"),
                "DOMECALT": (self.dome.CanSetAltitude, "Can dome set altitude"),
                "DOMECAZ": (self.dome.CanSetAzimuth, "Can dome set azimuth"),
                "DOMECSHT": (self.dome.CanSetShutter, "Can dome set shutter"),
                "DOMECSLV": (self.dome.CanSlave, "Can dome slave to mount"),
                "DCANSYNC": (
                    self.dome.CanSyncAzimuth,
                    "Can dome sync to azimuth value",
                ),
                "DCANHOME": (self.dome.CanFindHome, "Can dome home"),
                "DCANPARK": (self.dome.CanPark, "Can dome park"),
                "DCANSPRK": (self.dome.CanSetPark, "Can dome set park"),
                "DOMSUPAC": (str(self.dome.SupportedActions), "Dome supported actions"),
            }
            try:
                info["DOMEALT"] = (self.dome.Altitude, info["DOMEALT"][1])
            except:
                pass
            try:
                info["DOMEAZ"] = (self.dome.Azimuth, info["DOMEAZ"][1])
            except:
                pass
            try:
                info["DOMESHUT"] = (self.dome.ShutterStatus, info["DOMESHUT"][1])
            except:
                pass
            try:
                info["DOMESLAV"] = (self.dome.Slaved, info["DOMESLAV"][1])
            except:
                pass
            try:
                info["DOMEHOME"] = (self.dome.AtHome, info["DOMEHOME"][1])
            except:
                pass
            try:
                info["DOMEPARK"] = (self.dome.AtPark, info["DOMEPARK"][1])
            except:
                pass
            return info
        else:
            return {"DOMECONN": (False, "Dome connected")}

    @property
    def filter_wheel_info(self):
        logger.debug("Observatory.filter_wheel_info() called")
        if self.filter_wheel is not None:
            try:
                self.filter_wheel.Connected = True
            except:
                return {"FWCONN": (False, "Filter wheel connected")}
            info = {
                "FWCONN": (True, "Filter wheel connected"),
                "FWPOS": (self.filter_wheel.Position, "Filter wheel position"),
                "FWNAME": (
                    self.filter_wheel.Names[self.filter_wheel.Position],
                    "Filter wheel name (from filter wheel object configuration)",
                ),
                "FILTER": (
                    self.filters[self.filter_wheel.Position],
                    "Filter name (from pyscope observatory object configuration)",
                ),
                "FOCOFFCG": (
                    None,
                    "Filter focus offset (from filter wheel object configuration)",
                ),
                "FWNAME": (self.filter_wheel.Name, "Filter wheel name"),
                "FWDRVER": (
                    None,
                    "Filter wheel driver version",
                ),
                "FWDRV": (
                    None,
                    "Filter wheel driver info",
                ),
                "FWINTF": (
                    None,
                    "Filter wheel interface version",
                ),
                "FWDESC": (None, "Filter wheel description"),
                "FWALLNAM": (str(self.filter_wheel.Names), "Filter wheel names"),
                "FWALLOFF": (
                    None,
                    "Filter wheel focus offsets",
                ),
                "FWSUPAC": (
                    None,
                    "Filter wheel supported actions",
                ),
            }
            try:
                info["FOCOFFCG"] = (
                    self.filter_wheel.FocusOffsets[self.filter_wheel.Position],
                    info["FOCOFFCG"][1],
                )
            except:
                pass
            try:
                info["FWDRVER"] = (
                    self.filter_wheel.DriverVersion,
                    info["FWDRVER"][1],
                )
            except:
                pass
            try:
                info["FWDRV"] = (
                    str(self.filter_wheel.DriverInfo),
                    info["FWDRV"][1],
                )
            except:
                pass
            try:
                info["FWINTF"] = (
                    self.filter_wheel.InterfaceVersion,
                    info["FWINTF"][1],
                )
            except:
                pass
            try:
                info["FWDESC"] = (
                    self.filter_wheel.Description,
                    info["FWDESC"][1],
                )
            except:
                pass
            try:
                info["FWSUPAC"] = (
                    str(self.filter_wheel.SupportedActions),
                    info["FWSUPAC"][1],
                )
            except:
                pass
            try:
                info["FWALLOFF"] = (
                    str(self.filter_wheel.FocusOffsets),
                    info["FWALLOFF"][1],
                )
            except:
                pass
            return info
        else:
            return {"FWCONN": (False, "Filter wheel connected")}

    @property
    def focuser_info(self):
        logger.debug("Observatory.focuser_info() called")
        if self.focuser is not None:
            try:
                self.focuser.Connected = True
            except:
                return {"FOCCONN": (False, "Focuser connected")}
            info = {
                "FOCCONN": (True, "Focuser connected"),
                "FOCPOS": (None, "Focuser position"),
                "FOCMOV": (self.focuser.IsMoving, "Focuser moving"),
                "TEMPCOMP": (None, "Focuser temperature compensation"),
                "FOCTEMP": (None, "Focuser temperature"),
                "FOCNAME": (self.focuser.Name, "Focuser name"),
                "FOCDRVER": (self.focuser.DriverVersion, "Focuser driver version"),
                "FOCDRV": (str(self.focuser.DriverInfo), "Focuser driver info"),
                "FOCINTF": (self.focuser.InterfaceVersion, "Focuser interface version"),
                "FOCDESC": (self.focuser.Description, "Focuser description"),
                "FOCSTEP": (None, "Focuser step size"),
                "FOCABSOL": (
                    self.focuser.Absolute,
                    "Can focuser move to absolute position",
                ),
                "FOCMAXIN": (None, "Focuser maximum increment"),
                "FOCMAXST": (None, "Focuser maximum step"),
                "FOCTEMPC": (
                    None,
                    "Focuser temperature compensation available",
                ),
            }
            try:
                info["FOCMAXIN"] = (self.focuser.MaxIncrement, info["FOCMAXIN"][1])
            except:
                pass
            try:
                info["FOCMAXST"] = (self.focuser.MaxStep, info["FOCMAXST"][1])
            except:
                pass
            try:
                info["FOCPOS"] = (self.focuser.Position, info["FOCPOS"][1])
            except:
                pass
            try:
                info["TEMPCOMP"] = (self.focuser.TempComp, info["TEMPCOMP"][1])
            except:
                pass
            try:
                info["FOCTEMP"] = (self.focuser.Temperature, info["FOCTEMP"][1])
            except:
                pass
            try:
                info["FOCSTEP"] = (self.focuser.StepSize, info["FOCSTEP"][1])
            except:
                pass
            return info
        else:
            return {"FOCCONN": (False, "Focuser connected")}

    @property
    def observatory_info(self):
        logger.debug("Observatory.observatory_info() called")
        info = {
            "OBSNAME": (self.site_name, "Observatory name"),
            "OBSINSTN": (self.instrument_name, "Instrument name"),
            "OBSINSTD": (self.instrument_description, "Instrument description"),
            "OBSLAT": (self.latitude.to_string(sep="dms"), "Observatory latitude"),
            "OBSLONG": (self.longitude.to_string(sep="dms"), "Observatory longitude"),
            "OBSELEV": (self.elevation, "Observatory altitude"),
            "OBSDIA": (self.diameter, "Observatory diameter"),
            "OBSFL": (self.focal_length, "Observatory focal length"),
            "XPIXSCAL": (self.pixel_scale[0], "Observatory x-pixel scale"),
            "YPIXSCAL": (self.pixel_scale[1], "Observatory y-pixel scale"),
        }
        return info

    @property
    def observing_conditions_info(self):
        logger.debug("Observatory.observing_conditions_info() called")
        if self.observing_conditions is not None:
            try:
                self.observing_conditions.Connected = True
            except:
                return {"WXCONN": (False, "Observing conditions connected")}
            info = {
                "WXCONN": (True, "Observing conditions connected"),
                "WXAVGTIM": (
                    self.observing_conditions.AveragePeriod,
                    "Observing conditions average period",
                ),
                "WXCLD": (None, "Observing conditions cloud cover"),
                "WXCLDUPD": (None, "Observing conditions cloud cover last updated"),
                "WCCLDD": (None, "Observing conditions cloud cover sensor description"),
                "WXDEW": (None, "Observing conditions dew point"),
                "WXDEWUPD": (None, "Observing conditions dew point last updated"),
                "WXDEWD": (None, "Observing conditions dew point sensor description"),
                "WXHUM": (None, "Observing conditions humidity"),
                "WXHUMUPD": (None, "Observing conditions humidity last updated"),
                "WXHUMD": (None, "Observing conditions humidity sensor description"),
                "WXPRES": (None, "Observing conditions pressure"),
                "WXPREUPD": (None, "Observing conditions pressure last updated"),
                "WXPRESD": (None, "Observing conditions pressure sensor description"),
                "WXRAIN": (None, "Observing conditions rain rate"),
                "WXRAIUPD": (None, "Observing conditions rain rate last updated"),
                "WXRAIND": (None, "Observing conditions rain rate sensor description"),
                "WXSKY": (None, "Observing conditions sky brightness"),
                "WXSKYUPD": (None, "Observing conditions sky brightness last updated"),
                "WXSKYD": (
                    None,
                    "Observing conditions sky brightness sensor description",
                ),
                "WXSKYQ": (None, "Observing conditions sky quality"),
                "WXSKYQUP": (None, "Observing conditions sky quality last updated"),
                "WXSKYQD": (
                    None,
                    "Observing conditions sky quality sensor description",
                ),
                "WXSKYTMP": (None, "Observing conditions sky temperature"),
                "WXSKTUPD": (None, "Observing conditions sky temperature last updated"),
                "WXSKTD": (
                    None,
                    "Observing conditions sky temperature sensor description",
                ),
                "WXFWHM": (None, "Observing conditions seeing"),
                "WXFWHUP": (None, "Observing conditions seeing last updated"),
                "WXFWHMD": (None, "Observing conditions seeing sensor description"),
                "WXTEMP": (None, "Observing conditions temperature"),
                "WXTEMUPD": (None, "Observing conditions temperature last updated"),
                "WXTEMPD": (
                    None,
                    "Observing conditions temperature sensor description",
                ),
                "WXWIND": (None, "Observing conditions wind speed"),
                "WXWINUPD": (None, "Observing conditions wind speed last updated"),
                "WXWINDD": (None, "Observing conditions wind speed sensor description"),
                "WXWINDIR": (None, "Observing conditions wind direction"),
                "WXWDIRUP": (None, "Observing conditions wind direction last updated"),
                "WXWDIRD": (
                    None,
                    "Observing conditions wind direction sensor description",
                ),
                "WXWDGST": (
                    None,
                    "Observing conditions wind gust over last two minutes",
                ),
                "WXWGDUPD": (None, "Observing conditions wind gust last updated"),
                "WXWGDSTD": (None, "Observing conditions wind gust sensor description"),
                "WXNAME": (self.observing_conditions.Name, "Observing conditions name"),
                "WXDRVER": (
                    self.observing_conditions.DriverVersion,
                    "Observing conditions driver version",
                ),
                "WXDRIV": (
                    str(self.observing_conditions.DriverInfo),
                    "Observing conditions driver info",
                ),
                "WXINTF": (
                    self.observing_conditions.InterfaceVersion,
                    "Observing conditions interface version",
                ),
                "WXDESC": (
                    self.observing_conditions.Description,
                    "Observing conditions description",
                ),
            }
            try:
                info["WXCLD"] = (self.observing_conditions.CloudCover, info["WXCLD"][1])
                info["WXCLDUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("CloudCover"),
                    info["WXCLDUPD"][1],
                )
                info["WXCLDD"] = (
                    self.observing_conditions.SensorDescription("CloudCover"),
                    info["WXCLDD"][1],
                )
            except:
                pass
            try:
                info["WXDEW"] = (self.observing_conditions.DewPoint, info["WXDEW"][1])
                info["WXDEWUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("DewPoint"),
                    info["WXDEWUPD"][1],
                )
                info["WXDEWD"] = (
                    self.observing_conditions.SensorDescription("DewPoint"),
                    info["WXDEWD"][1],
                )
            except:
                pass
            try:
                info["WXHUM"] = (self.observing_conditions.Humidity, info["WXHUM"][1])
                info["WXHUMUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("Humidity"),
                    info["WXHUMUPD"][1],
                )
                info["WXHUMD"] = (
                    self.observing_conditions.SensorDescription("Humidity"),
                    info["WXHUMD"][1],
                )
            except:
                pass
            try:
                info["WXPRES"] = (self.observing_conditions.Pressure, info["WXPRES"][1])
                info["WXPREUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("Pressure"),
                    info["WXPREUPD"][1],
                )
                info["WXPRESD"] = (
                    self.observing_conditions.SensorDescription("Pressure"),
                    info["WXPRESD"][1],
                )
            except:
                pass
            try:
                info["WXRAIN"] = (self.observing_conditions.RainRate, info["WXRAIN"][1])
                info["WXRAIUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("RainRate"),
                    info["WXRAIUPD"][1],
                )
                info["WXRAIND"] = (
                    self.observing_conditions.SensorDescription("RainRate"),
                    info["WXRAIND"][1],
                )
            except:
                pass
            try:
                info["WXSKY"] = (
                    self.observing_conditions.SkyBrightness,
                    info["WXSKY"][1],
                )
                info["WXSKYUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("SkyBrightness"),
                    info["WXSKYUPD"][1],
                )
                info["WXSKYD"] = (
                    self.observing_conditions.SensorDescription("SkyBrightness"),
                    info["WXSKYD"][1],
                )
            except:
                pass
            try:
                info["WXSKYQ"] = (
                    self.observing_conditions.SkyQuality,
                    info["WXSKYQ"][1],
                )
                info["WXSKYQUP"] = (
                    self.observing_conditions.TimeSinceLastUpdate("SkyQuality"),
                    info["WXSKYQUP"][1],
                )
                info["WXSKYQD"] = (
                    self.observing_conditions.SensorDescription("SkyQuality"),
                    info["WXSKYQD"][1],
                )
            except:
                pass
            try:
                info["WXSKYTMP"] = (
                    self.observing_conditions.SkyTemperature,
                    info["WXSKYTMP"][1],
                )
                info["WXSKTUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("SkyTemperature"),
                    info["WXSKTUPD"][1],
                )
                info["WXSKTD"] = (
                    self.observing_conditions.SensorDescription("SkyTemperature"),
                    info["WXSKTD"][1],
                )
            except:
                pass
            try:
                info["WXFWHM"] = (
                    self.observing_conditions.WindSpeed,
                    info["WXFWHM"][1],
                )
                info["WXFWHUP"] = (
                    self.observing_conditions.TimeSinceLastUpdate("WindSpeed"),
                    info["WXFWHUP"][1],
                )
                info["WXFWHMD"] = (
                    self.observing_conditions.SensorDescription("WindSpeed"),
                    info["WXFWHMD"][1],
                )
            except:
                pass
            try:
                info["WXTEMP"] = (
                    self.observing_conditions.Temperature,
                    info["WXTEMP"][1],
                )
                info["WXTEMUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("Temperature"),
                    info["WXTEMUPD"][1],
                )
                info["WXTEMPD"] = (
                    self.observing_conditions.SensorDescription("Temperature"),
                    info["WXTEMPD"][1],
                )
            except:
                pass
            try:
                info["WXWIND"] = (
                    self.observing_conditions.WindSpeed,
                    info["WXWIND"][1],
                )
                info["WXWINUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("WindSpeed"),
                    info["WXWINUPD"][1],
                )
                info["WXWINDD"] = (
                    self.observing_conditions.SensorDescription("WindSpeed"),
                    info["WXWINDD"][1],
                )
            except:
                pass
            try:
                info["WXWINDIR"] = (
                    self.observing_conditions.WindDirection,
                    info["WXWINDIR"][1],
                )
                info["WXWDIRUP"] = (
                    self.observing_conditions.TimeSinceLastUpdate("WindDirection"),
                    info["WXWDIRUP"][1],
                )
                info["WXWDIRD"] = (
                    self.observing_conditions.SensorDescription("WindDirection"),
                    info["WXWDIRD"][1],
                )
            except:
                pass
            try:
                info["WXWDGST"] = (
                    self.observing_conditions.WindGust,
                    info["WXWDGST"][1],
                )
                info["WXWGDUPD"] = (
                    self.observing_conditions.TimeSinceLastUpdate("WindGust"),
                    info["WXWGDUPD"][1],
                )
                info["WXWGDSTD"] = (
                    self.observing_conditions.SensorDescription("WindGust"),
                    info["WXWGDSTD"][1],
                )
            except:
                pass
            try:
                info["WXAVGTIM"] = (
                    self.observing_conditions.AveragePeriod,
                    info["WXAVGTIM"][1],
                )
            except:
                pass
            return info
        else:
            return {"WXCONN": (False, "Observing conditions connected")}

    @property
    def rotator_info(self):
        logger.debug("Observatory.rotator_info() called")
        if self.rotator is not None:
            try:
                self.rotator.Connected = True
            except:
                return {"ROTCONN": (False, "Rotator connected")}
            info = {
                "ROTCONN": (True, "Rotator connected"),
                "ROTPOS": (self.rotator.Position, "Rotator position"),
                "ROTMECHP": (
                    self.rotator.MechanicalPosition,
                    "Rotator mechanical position",
                ),
                "ROTTARGP": (self.rotator.TargetPosition, "Rotator target position"),
                "ROTMOV": (self.rotator.IsMoving, "Rotator moving"),
                "ROTREVSE": (self.rotator.Reverse, "Rotator reverse"),
                "ROTNAME": (self.rotator.Name, "Rotator name"),
                "ROTDRVER": (self.rotator.DriverVersion, "Rotator driver version"),
                "ROTDRV": (str(self.rotator.DriverInfo), "Rotator driver name"),
                "ROTINTFC": (
                    self.rotator.InterfaceVersion,
                    "Rotator interface version",
                ),
                "ROTDESC": (self.rotator.Description, "Rotator description"),
                "ROTSTEP": (None, "Rotator step size [degrees]"),
                "ROTCANRV": (self.rotator.CanReverse, "Can rotator reverse"),
                "ROTSUPAC": (
                    str(self.rotator.SupportedActions),
                    "Rotator supported actions",
                ),
            }
            try:
                info["ROTSTEP"] = (self.rotator.StepSize, info["ROTSTEP"][1])
            except:
                pass
            return info
        else:
            return {"ROTCONN": (False, "Rotator connected")}

    @property
    def safety_monitor_info(self, index=None):
        logger.debug("Observatory.safety_monitor_info() called")
        if self.safety_monitor is not None:
            all_info = []
            for i in range(len(self.safety_monitor)):
                try:
                    self.safety_monitor[i].Connected = True
                    # Should likely be broken into multiple try/except blocks
                    info = {
                        ("SM%iCONN" % i): (True, "Safety monitor connected"),
                        ("SM%iISSAF" % i): (
                            self.safety_monitor[i].IsSafe,
                            "Safety monitor safe",
                        ),
                        ("SM%iNAME" % i): (
                            self.safety_monitor[i].Name,
                            "Safety monitor name",
                        ),
                        ("SM%iDRVER" % i): (
                            self.safety_monitor[i].DriverVersion,
                            "Safety monitor driver version",
                        ),
                        ("SM%iDRV" % i): (
                            str(self.safety_monitor[i].DriverInfo),
                            "Safety monitor driver name",
                        ),
                        ("SM%iINTF" % i): (
                            self.safety_monitor[i].InterfaceVersion,
                            "Safety monitor interface version",
                        ),
                        ("SM%iDESC" % i): (
                            self.safety_monitor[i].Description,
                            "Safety monitor description",
                        ),
                        ("SM%iSUPAC" % i): (
                            str(self.safety_monitor[i].SupportedActions),
                            "Safety monitor supported actions",
                        ),
                    }
                except:
                    info = {"SM%iCONN" % i: (False, "Safety monitor connected")}

                all_info.append(info)
        else:
            return {"SM0CONN": (False, "Safety monitor connected")}

        if index is not None:
            return all_info[index]
        elif len(all_info) == 1:
            return all_info[0]
        else:
            return all_info

    @property
    def switch_info(self, index=None):
        logger.debug("Observatory.switch_info() called")
        if self.switch is not None:
            all_info = []
            for i in range(len(self.switch)):
                try:
                    self.switch.Connected = True
                    try:
                        info = {
                            ("SW%iCONN" % i): (True, "Switch connected"),
                            ("SW%iNAME" % i): (self.switch[i].Name, "Switch name"),
                            ("SW%iDRVER" % i): (
                                self.switch[i].DriverVersion,
                                "Switch driver version",
                            ),
                            ("SW%iDRV" % i): (
                                str(self.switch[i].DriverInfo),
                                "Switch driver name",
                            ),
                            ("SW%iINTF" % i): (
                                self.switch[i].InterfaceVersion,
                                "Switch interface version",
                            ),
                            ("SW%iDESC" % i): (
                                self.switch[i].Description,
                                "Switch description",
                            ),
                            ("SW%iSUPAC" % i): (
                                str(self.switch[i].SupportedActions),
                                "Switch supported actions",
                            ),
                            ("SW%iMAXSW" % i): (
                                self.switch[i].MaxSwitch,
                                "Switch maximum switch",
                            ),
                        }
                        for j in range(self.switch[i].MaxSwitch):
                            try:
                                info[("SW%iSW%iNM" % (i, j))] = (
                                    self.switch[i].GetSwitchName(j),
                                    "Switch %i Device %i name" % (i, j),
                                )
                                info[("SW%iSW%iDS" % (i, j))] = (
                                    self.switch[i].GetSwitchDescription(j),
                                    "Switch %i Device %i description" % (i, j),
                                )
                                info[("SW%iSW%i" % (i, j))] = (
                                    self.switch[i].GetSwitch(j),
                                    "Switch %i Device %i state" % (i, j),
                                )
                                info[("SW%iSW%iMN" % (i, j))] = (
                                    self.switch[i].MinSwitchValue(j),
                                    "Switch %i Device %i minimum value" % (i, j),
                                )
                                info[("SW%iSW%iMX" % (i, j))] = (
                                    self.switch[i].MaxSwitchValue(j),
                                    "Switch %i Device %i maximum value" % (i, j),
                                )
                                info[("SW%iSW%iST" % (i, j))] = (
                                    self.switch[i].SwitchStep(j),
                                    "Switch %i Device %i step" % (i, j),
                                )
                            except Exception as e:
                                logger.debug(
                                    f"Sub-switch {j} of switch {i} gave the following error: {e}"
                                )
                    except Exception as e:
                        logger.debug(f"Switch {i} gives the following error: {e}")
                except:
                    info = {("SW%iCONN" % i): (False, "Switch connected")}

                all_info.append(info)
        else:
            return {"SW0CONN": (False, "Switch connected")}

        if index is not None:
            return all_info[index]
        elif len(all_info) == 1:
            return all_info[0]
        else:
            return all_info

    @property
    def telescope_info(self):
        logger.debug("Observatory.telescope_info() called")
        try:
            self.telescope.Connected = True
        except:
            return {"TELCONN": (False, "Telescope connected")}
        info = {
            "TELCONN": (True, "Telescope connected"),
            "TELHOME": (self.telescope.AtHome, "Is telescope at home position"),
            "TELPARK": (self.telescope.AtPark, "Is telescope at park position"),
            "TELALT": (None, "Telescope altitude [degrees]"),
            "TELAZ": (
                None,
                "Telescope azimuth North-referenced positive East (clockwise) [degrees]",
            ),
            "TELRA": (
                self.telescope.RightAscension,
                "Telescope right ascension in TELEQSYS coordinate frame [hours]",
            ),
            "TELDEC": (
                self.telescope.Declination,
                "Telescope declination in TELEQSYS coordinate frame [degrees]",
            ),
            "TELRAIC": (
                None,
                "Telescope right ascension in ICRS coordinate frame [hours]",
            ),
            "TELDECIC": (
                None,
                "Telescope declination in ICRS coordinate frame [degrees]",
            ),
            "TARGRA": (
                None,
                "Telescope target right ascension in TELEQSYS coordinate frame [hours]",
            ),
            "TARGDEC": (
                None,
                "Telescope target declination in TELEQSYS coordinate frame [degrees]",
            ),
            "OBJCTALT": (None, "Object altitude [degrees]"),
            "OBJCTAZ": (
                None,
                "Object azimuth North-referenced positive East (clockwise) [degrees]",
            ),
            "OBJCTHA": (None, "Object hour angle [hours]"),
            "AIRMASS": (None, "Airmass"),
            "MOONANGL": (None, "Angle between object and moon [degrees]"),
            "MOONPHAS": (None, "Moon phase [percent]"),
            "TELSLEW": (None, "Is telescope slewing"),
            "TELSETT": (None, "Telescope settling time [seconds]"),
            "TELPIER": (None, "Telescope pier side"),
            "TELTRACK": (None, "Is telescope tracking"),
            "TELTRKRT": (None, "Telescope tracking rate (sidereal)"),
            "TELOFFRA": (
                None,
                "Telescope RA tracking offset [seconds per sidereal second]",
            ),
            "TELOFFDC": (
                None,
                "Telescope DEC tracking offset [arcseconds per sidereal second]",
            ),
            "TELPULSE": (None, "Is telescope pulse guiding"),
            "TELGUIDR": (None, "Telescope pulse guiding RA rate [degrees/sec]"),
            "TELGUIDD": (None, "Telescope pulse guiding DEC rate [arcseconds/sec]"),
            "TELDOREF": (None, "Does telescope do refraction"),
            "TELLST": (
                self.telescope.SiderealTime,
                "Telescope local sidereal time [hours]",
            ),
            "TELUT": (None, "Telescope UTC date"),
            "TELNAME": (self.telescope.Name, "Telescope name"),
            "TELDRVER": (self.telescope.DriverVersion, "Telescope driver version"),
            "TELDRV": (str(self.telescope.DriverInfo), "Telescope driver name"),
            "TELINTF": (self.telescope.InterfaceVersion, "Telescope interface version"),
            "TELDESC": (self.telescope.Description, "Telescope description"),
            "TELAPAR": (None, "Telescope aperture area [m^2]"),
            "TELDIAM": (None, "Telescope aperture diameter [m]"),
            "TELFOCL": (None, "Telescope focal length [m]"),
            "TELELEV": (None, "Telescope elevation [degrees]"),
            "TELLAT": (None, "Telescope latitude [degrees]"),
            "TELLONG": (None, "Telescope longitude [degrees]"),
            "TELALN": (None, "Telescope alignment mode"),
            "TELEQSYS": (
                ["equOther", "equTopocentric", "equJ2000", "equJ2050", "equB1950"][
                    self.telescope.EquatorialSystem
                ],
                "Telescope equatorial coordinate system",
            ),
            "TELCANHM": (self.telescope.CanFindHome, "Can telescope find home"),
            "TELCANPA": (self.telescope.CanPark, "Can telescope park"),
            "TELCANUN": (self.telescope.CanUnpark, "Can telescope unpark"),
            "TELCANPP": (self.telescope.CanSetPark, "Can telescope set park position"),
            # "TELCANPG": (self.telescope.CanPulseGuide, "Can telescope pulse guide"),
            "TELCANGR": (
                self.telescope.CanSetGuideRates,
                "Can telescope set guide rates",
            ),
            "TELCANTR": (self.telescope.CanSetTracking, "Can telescope set tracking"),
            "TELCANSR": (
                self.telescope.CanSetRightAscensionRate,
                "Can telescope set RA offset rate",
            ),
            "TELCANSD": (
                self.telescope.CanSetDeclinationRate,
                "Can telescope set DEC offset rate",
            ),
            "TELCANSP": (self.telescope.CanSetPierSide, "Can telescope set pier side"),
            "TELCANSL": (
                self.telescope.CanSlew,
                "Can telescope slew to equatorial coordinates",
            ),
            "TELCNSLA": (
                self.telescope.CanSlewAsync,
                "Can telescope slew asynchronously",
            ),
            "TELCANSF": (
                self.telescope.CanSlewAltAz,
                "Can telescope slew to alt-azimuth coordinates",
            ),
            "TELCNSFA": (
                self.telescope.CanSlewAltAzAsync,
                "Can telescope slew to alt-azimuth coordinates asynchronously",
            ),
            "TELCANSY": (
                self.telescope.CanSync,
                "Can telescope sync to equatorial coordinates",
            ),
            "TELCNSYA": (
                self.telescope.CanSyncAltAz,
                "Can telescope sync to alt-azimuth coordinates",
            ),
            "TELTRCKS": (str(self.telescope.TrackingRates), "Telescope tracking rates"),
            "TELSUPAC": (
                None,
                "Telescope supported actions",
            ),
        }
        # Sometimes, TELDRV has /r or /n in it and it breaks
        # This is a hack to fix that
        info["TELDRV"] = (
            info["TELDRV"][0].replace("\r", "\\r").replace("\n", "\\n"),
            info["TELDRV"][1],
        )
        info["TELDRV"] = (
            "".join([i if ord(i) < 128 else " " for i in info["TELDRV"][0]]),
            info["TELDRV"][1],
        )
        try:
            info["TELALT"] = (self.telescope.Altitude, info["TELALT"][1])
        except:
            pass
        try:
            info["TELAZ"] = (self.telescope.Azimuth, info["TELAZ"][1])
        except:
            pass
        try:
            info["TARGRA"] = (self.telescope.TargetRightAscension, info["TARGRA"][1])
        except:
            pass
        try:
            info["TARGDEC"] = (self.telescope.TargetDeclination, info["TARGDEC"][1])
        except:
            pass
        obj = self.get_current_object()
        info["TELRAIC"] = (obj.ra.to_string(unit=u.hour), info["TELRAIC"][1])
        info["TELDECIC"] = (obj.dec.to_string(unit=u.degree), info["TELDECIC"][1])
        info["OBJCTALT"] = (
            obj.transform_to(
                coord.AltAz(
                    obstime=self.observatory_time, location=self.observatory_location
                )
            )
            .alt.to(u.degree)
            .value,
            info["OBJCTALT"][1],
        )
        info["OBJCTAZ"] = (
            obj.transform_to(
                coord.AltAz(
                    obstime=self.observatory_time, location=self.observatory_location
                )
            )
            .az.to(u.degree)
            .value,
            info["OBJCTAZ"][1],
        )
        info["OBJCTHA"] = ((self.lst() - obj.ra).value, info["OBJCTHA"][1])
        info["AIRMASS"] = (
            airmass(
                obj.transform_to(
                    coord.AltAz(
                        obstime=self.observatory_time,
                        location=self.observatory_location,
                    )
                )
                .alt.to(u.rad)
                .value
            ),
            info["AIRMASS"][1],
        )
        info["MOONANGL"] = (
            coord.get_body(
                "moon", self.observatory_time, location=self.observatory_location
            )
            .separation(obj)
            .to(u.degree)
            .value,
            info["MOONANGL"][1],
        )
        info["MOONPHAS"] = (
            self.moon_illumination(self.observatory_time),
            info["MOONPHAS"][1],
        )
        try:
            info["TELSLEW"] = (self.telescope.Slewing, info["TELSLEW"][1])
        except:
            pass
        try:
            info["TELSETT"] = (self.telescope.SlewSettleTime, info["TELSETT"][1])
        except:
            pass
        try:
            info["TELPIER"] = (
                ["pierEast", "pierWest", "pierUnknown"][self.telescope.SideOfPier],
                info["TELPIER"][1],
            )
        except:
            pass
        try:
            info["TELTRACK"] = (self.telescope.Tracking, info["TELTRACK"][1])
        except:
            pass
        try:
            info["TELTRKRT"] = (
                self.telescope.TrackingRates[self.telescope.TrackingRate],
                info["TELTRKRT"][1],
            )
        except:
            pass
        try:
            info["TELOFFRA"] = (self.telescope.RightAscensionRate, info["TELOFFRA"][1])
        except:
            pass
        try:
            info["TELOFFDC"] = (self.telescope.DeclinationRate, info["TELOFFDC"][1])
        except:
            pass
        try:
            info["TELPULSE"] = (self.telescope.IsPulseGuiding, info["TELPULSE"][1])
        except:
            pass
        try:
            info["TELGUIDR"] = (
                self.telescope.GuideRateRightAscension,
                info["TELGUIDR"][1],
            )
        except:
            pass
        try:
            info["TELGUIDD"] = (
                self.telescope.GuideRateDeclination,
                info["TELGUIDD"][1],
            )
        except:
            pass
        try:
            info["TELDOREF"] = (self.telescope.DoesRefraction, info["TELDOREF"][1])
        except:
            pass
        try:
            info["TELUT"] = (
                # self.telescope.UTCDate.strftime("%Y-%m-%dT%H:%M:%S"),
                self.observatory_time.strftime("%Y-%m-%dT%H:%M:%S"),
                info["TELUT"][1],
            )
        except:
            pass
        try:
            info["TELAPAR"] = (self.telescope.ApertureArea, info["TELAPAR"][1])
        except:
            pass
        try:
            info["TELDIAM"] = (self.telescope.ApertureDiameter, info["TELDIAM"][1])
        except:
            pass
        try:
            info["TELFOCL"] = (self.telescope.FocalLength, info["TELFOCL"][1])
        except:
            pass
        try:
            info["TELELEV"] = (self.telescope.SiteElevation, info["TELELEV"][1])
        except:
            pass
        try:
            info["TELLAT"] = (self.telescope.SiteLatitude, info["TELLAT"][1])
        except:
            pass
        try:
            info["TELLONG"] = (self.telescope.SiteLongitude, info["TELLONG"][1])
        except:
            pass
        try:
            info["TELALN"] = (
                ["AltAz", "Polar", "GermanPolar"][self.telescope.AlignmentMode],
                info["TELALN"][1],
            )
        except:
            pass
        try:
            info["TELSUPAC"] = (
                str(self.telescope.SupportedActions),
                info["TELSUPAC"][1],
            )
        except:
            pass
        return info

    @property
    def threads_info(self):
        logger.debug("Observatory.threads_info() called")
        info = {
            "DEROTATE": (
                not self._derotation_thread is None,
                "Is derotation thread active",
            ),
            "OCTHREAD": (
                not self._observing_conditions_thread is None,
                "Is observing conditions thread active",
            ),
            "SMTHREAD": (
                not self._safety_monitor_thread is None,
                "Is status monitor thread active",
            ),
        }
        return info

    @property
    def observatory_location(self):
        """Returns the EarthLocation object for the observatory"""
        logger.debug("Observatory.observatory_location() called")
        return coord.EarthLocation(
            lat=self.latitude, lon=self.longitude, height=self.elevation
        )

    @property
    def observatory_time(self):
        """Returns the current observatory time"""
        logger.debug("Observatory.observatory_time() called")
        return astrotime.Time.now()

    @property
    def plate_scale(self):
        """Returns the plate scale of the telescope in arcsec/mm"""
        logger.debug("Observatory.plate_scale() called")
        return 206265 / self.focal_length

    @property
    def pixel_scale(self):
        """Returns the pixel scale of the camera"""
        logger.debug("Observatory.pixel_scale() called")
        return (
            self.plate_scale * self.camera.PixelSizeX * 1e-6,
            self.plate_scale * self.camera.PixelSizeY * 1e-6,
        )

    @property
    def site_name(self):
        logger.debug("Observatory.site_name property called")
        return self._site_name

    @site_name.setter
    def site_name(self, value):
        logger.debug(f"Observatory.site_name = {value} called")
        self._site_name = value if value is not None or value != "" else None
        self._config["site"]["site_name"] = (
            self._site_name if self._site_name is not None else ""
        )

    @property
    def instrument_name(self):
        logger.debug("Observatory.instrument_name property called")
        return self._instrument_name

    @instrument_name.setter
    def instrument_name(self, value):
        logger.debug(f"Observatory.instrument_name = {value} called")
        self._instrument_name = value if value is not None or value != "" else None
        self._config["site"]["instrument_name"] = (
            self._instrument_name if self._instrument_name is not None else ""
        )

    @property
    def instrument_description(self):
        logger.debug("Observatory.instrument_description property called")
        return self._instrument_description

    @instrument_description.setter
    def instrument_description(self, value):
        logger.debug(f"Observatory.instrument_description = {value} called")
        self._instrument_description = (
            value if value is not None or value != "" else None
        )
        self._config["site"]["instrument_description"] = (
            self._instrument_description
            if self._instrument_description is not None
            else ""
        )

    @property
    def latitude(self):
        logger.debug("Observatory.latitude property called")
        return self._latitude

    @latitude.setter
    def latitude(self, value):
        logger.debug(f"Observatory.latitude = {value} called")
        self._latitude = (
            coord.Latitude(value) if value is not None or value != "" else None
        )
        # If connected, set the telescope site latitude
        try:
            if self.telescope.Connected:
                self.telescope.SiteLatitude = self._latitude.deg
        except:
            logger.warning("Telescope not connected, cannot set the driver's latitude")

        self._config["site"]["latitude"] = (
            self._latitude.to_string(unit=u.degree, sep="dms", precision=5)
            if self._latitude is not None
            else ""
        )

    @property
    def longitude(self):
        logger.debug("Observatory.longitude property called")
        return self._longitude

    @longitude.setter
    def longitude(self, value):
        logger.debug(f"Observatory.longitude = {value} called")
        self._longitude = (
            coord.Longitude(value, wrap_angle=180 * u.deg)
            if value is not None or value != ""
            else None
        )
        try:
            if self.telescope.Connected:
                self.telescope.SiteLongitude = self._longitude.deg
        except:
            logger.warning("Telescope not connected, cannot set the driver's longitude")

        self._config["site"]["longitude"] = (
            self._longitude.to_string(unit=u.degree, sep="dms", precision=5)
            if self._longitude is not None
            else ""
        )

    @property
    def elevation(self):
        logger.debug("Observatory.elevation property called")
        return self._elevation

    @elevation.setter
    def elevation(self, value):
        logger.debug(f"Observatory.elevation = {value} called")
        self._elevation = (
            max(float(value), 0) if value is not None or value != "" else None
        )
        self._config["site"]["elevation"] = (
            str(self._elevation) if self._elevation is not None else ""
        )

    @property
    def diameter(self):
        logger.debug("Observatory.diameter property called")
        return self._diameter

    @diameter.setter
    def diameter(self, value):
        logger.debug(f"Observatory.diameter = {value} called")
        self._diameter = (
            max(float(value), 0) if value is not None or value != "" else None
        )
        self._config["site"]["diameter"] = (
            str(self._diameter) if self._diameter is not None else ""
        )

    @property
    def focal_length(self):
        logger.debug("Observatory.focal_length property called")
        return self._focal_length

    @focal_length.setter
    def focal_length(self, value):
        logger.debug(f"Observatory.focal_length = {value} called")
        self._focal_length = (
            max(float(value), 0) if value is not None or value != "" else None
        )
        self._config["site"]["focal_length"] = (
            str(self._focal_length) if self._focal_length is not None else ""
        )

    @property
    def camera(self):
        logger.debug("Observatory.camera property called")
        return self._camera

    @property
    def camera_driver(self):
        logger.debug("Observatory.camera_driver property called")
        return self._camera_driver

    @property
    def camera_kwargs(self):
        logger.debug("Observatory.camera_kwargs property called")
        return self._camera_kwargs

    @property
    def cooler_setpoint(self):
        logger.debug("Observatory.cooler_setpoint property called")
        return self._cooler_setpoint

    @cooler_setpoint.setter
    def cooler_setpoint(self, value):
        logger.debug(f"Observatory.cooler_setpoint = {value} called")
        if value is not None:
            self._cooler_setpoint = value if value is not None or value != "" else None
            self._config["camera"]["cooler_setpoint"] = (
                str(self._cooler_setpoint) if self._cooler_setpoint is not None else ""
            )
        else:
            self._cooler_setpoint = None
            self._config["camera"]["cooler_setpoint"] = ""
        try:
            if self.camera.CanSetCCDTemperature and self._cooler_setpoint is not None:
                self.camera.SetCCDTemperature = self._cooler_setpoint
                logger.info(f"CCD Temp Set to {self._cooler_setpoint}")
            else:
                self._cooler_setpoint = None
                self._config["camera"]["cooler_setpoint"] = ""
                logger.warning("Camera does not support setting the CCD temperature")
        except:
            pass

    @property
    def cooler_tolerance(self):
        logger.debug("Observatory.cooler_tolerance property called")
        return self._cooler_tolerance

    @cooler_tolerance.setter
    def cooler_tolerance(self, value):
        logger.debug(f"Observatory.cooler_tolerance = {value} called")
        self._cooler_tolerance = (
            max(float(value), 0) if value is not None or value != "" else None
        )
        self._config["camera"]["cooler_tolerance"] = (
            str(self._cooler_tolerance) if self._cooler_tolerance is not None else ""
        )

    @property
    def max_dimension(self):
        logger.debug("Observatory.max_dimension property called")
        return self._max_dimension

    @max_dimension.setter
    def max_dimension(self, value):
        logger.debug(f"Observatory.max_dimension = {value} called")
        self._max_dimension = (
            max(int(value), 1) if value is not None and value != "" else None
        )
        self._config["camera"]["max_dimension"] = (
            str(self._max_dimension) if self._max_dimension is not None else ""
        )
        if (
            self._max_dimension is not None
            and max(self.camera.CameraXSize, self.camera.CameraYSize)
            > self._max_dimension
        ):
            raise ObservatoryException(
                "Camera sensor size exceeds maximum dimension of %d"
                % self._max_dimension
            )

    @property
    def cover_calibrator(self):
        logger.debug("Observatory.cover_calibrator property called")
        return self._cover_calibrator

    @property
    def cover_calibrator_driver(self):
        logger.debug("Observatory.cover_calibrator_driver property called")
        return self._cover_calibrator_driver

    @property
    def cover_calibrator_kwargs(self):
        logger.debug("Observatory.cover_calibrator_kwargs property called")
        return self._cover_calibrator_kwargs

    @property
    def cover_calibrator_alt(self):
        logger.debug("Observatory.cover_calibrator_alt property called")
        return self._cover_calibrator_alt

    @cover_calibrator_alt.setter
    def cover_calibrator_alt(self, value):
        logger.debug(f"Observatory.cover_calibrator_alt = {value} called")
        self._cover_calibrator_alt = (
            min(max(float(value), 0), 90) if value is not None and value != "" else None
        )
        self._config["cover_calibrator"]["cover_calibrator_alt"] = (
            str(self._cover_calibrator_alt)
            if self._cover_calibrator_alt is not None
            else ""
        )

    @property
    def cover_calibrator_az(self):
        logger.debug("Observatory.cover_calibrator_az property called")
        return self._cover_calibrator_az

    @cover_calibrator_az.setter
    def cover_calibrator_az(self, value):
        logger.debug(f"Observatory.cover_calibrator_az = {value} called")
        self._cover_calibrator_az = (
            min(max(float(value), 0), 360)
            if value is not None and value != ""
            else None
        )
        self._config["cover_calibrator"]["cover_calibrator_az"] = (
            str(self._cover_calibrator_az)
            if self._cover_calibrator_az is not None
            else ""
        )

    @property
    def dome(self):
        logger.debug("Observatory.dome property called")
        return self._dome

    @property
    def dome_driver(self):
        logger.debug("Observatory.dome_driver property called")
        return self._dome_driver

    @property
    def dome_kwargs(self):
        logger.debug("Observatory.dome_kwargs property called")
        return self._dome_kwargs

    @property
    def filter_wheel(self):
        logger.debug("Observatory.filter_wheel property called")
        return self._filter_wheel

    @property
    def filter_wheel_driver(self):
        logger.debug("Observatory.filter_wheel_driver property called")
        return self._filter_wheel_driver

    @property
    def filter_wheel_kwargs(self):
        logger.debug("Observatory.filter_wheel_kwargs property called")
        return self._filter_wheel_kwargs

    @property
    def filters(self):
        logger.debug("Observatory.filters property called")
        return self._filters

    @filters.setter
    def filters(self, value, position=None):
        logger.debug(f"Observatory.filters = {value} called")
        if value is self._filters:
            return
        if type(value) is list:
            self._filters = value
        if position is None:
            self._filters = (
                [v for v in value.replace(" ", "").split(",")]
                if value is not None or value != ""
                else None
            )
        else:
            self._filters[position] = (
                str(value) if value is not None or value != "" else None
            )
        self._config["filter_wheel"]["filters"] = (
            ", ".join(self._filters) if self._filters is not None else ""
        )

    @property
    def filter_focus_offsets(self):
        logger.debug("Observatory.filter_focus_offsets property called")
        return self._filter_focus_offsets

    @filter_focus_offsets.setter
    def filter_focus_offsets(self, value, filt=None):
        logger.debug(f"Observatory.filter_focus_offsets = {value} called")
        if value is self._filter_focus_offsets:
            return
        if type(value) is dict:
            if value.keys() == self.filters:
                self._filter_focus_offsets = value
            else:
                raise ObservatoryException(
                    "Filter focus offsets dictionary must have keys matching filters"
                )
        if filt is None:
            self._filter_focus_offsets = (
                dict(zip(self.filters, [int(v) for v in value.split(",")]))
                if value is not None or value != ""
                else None
            )
        else:
            self._filter_focus_offsets[filt] = (
                int(value) if value is not None or value != "" else None
            )
        self._config["filter_wheel"]["filter_focus_offsets"] = (
            ",".join([str(v) for v in self._filter_focus_offsets.values()])
            if self._filter_focus_offsets is not None
            else ""
        )

    @property
    def focuser(self):
        logger.debug("Observatory.focuser property called")
        return self._focuser

    @property
    def focuser_driver(self):
        logger.debug("Observatory.focuser_driver property called")
        return self._focuser_driver

    @property
    def focuser_kwargs(self):
        logger.debug("Observatory.focuser_kwargs property called")
        return self._focuser_kwargs

    @property
    def observing_conditions(self):
        logger.debug("Observatory.observing_conditions property called")
        return self._observing_conditions

    @property
    def observing_conditions_driver(self):
        logger.debug("Observatory.observing_conditions_driver property called")
        return self._observing_conditions_driver

    @property
    def observing_conditions_kwargs(self):
        logger.debug("Observatory.observing_conditions_kwargs property called")
        return self._observing_conditions_kwargs

    @property
    def rotator(self):
        logger.debug("Observatory.rotator property called")
        return self._rotator

    @property
    def rotator_driver(self):
        logger.debug("Observatory.rotator_driver property called")
        return self._rotator_driver

    @property
    def rotator_kwargs(self):
        logger.debug("Observatory.rotator_kwargs property called")
        return self._rotator_kwargs

    @property
    def rotator_reverse(self):
        logger.debug("Observatory.rotator_reverse property called")
        return self._rotator_reverse

    @rotator_reverse.setter
    def rotator_reverse(self, value):
        logger.debug(f"Observatory.rotator_reverse = {value} called")
        self._rotator_reverse = (
            bool(value) if value is not None or value != "" else None
        )
        self._config["rotator"]["rotator_reverse"] = (
            str(self._rotator_reverse) if self._rotator_reverse is not None else ""
        )
        try:
            if self.rotator is not None:
                self.rotator.Reverse = self._rotator_reverse
        except:
            logger.warning(
                "Rotator not connected, you should reconnect to the rotator and then set the reverse property"
            )

    @property
    def rotator_min_angle(self):
        logger.debug("Observatory.rotator_min_angle property called")
        return self._rotator_min_angle

    @rotator_min_angle.setter
    def rotator_min_angle(self, value):
        logger.debug(f"Observatory.rotator_min_angle = {value} called")
        self._rotator_min_angle = (
            float(value) if value is not None or value != "" else None
        )
        self._config["rotator"]["rotator_min_angle"] = (
            str(self._rotator_min_angle) if self._rotator_min_angle is not None else ""
        )

    @property
    def rotator_max_angle(self):
        logger.debug("Observatory.rotator_max_angle property called")
        return self._rotator_max_angle

    @rotator_max_angle.setter
    def rotator_max_angle(self, value):
        logger.debug(f"Observatory.rotator_max_angle = {value} called")
        self._rotator_max_angle = (
            float(value) if value is not None or value != "" else None
        )
        self._config["rotator"]["rotator_max_angle"] = (
            str(self._rotator_max_angle) if self._rotator_max_angle is not None else ""
        )

    @property
    def safety_monitor(self):
        logger.debug("Observatory.safety_monitor property called")
        return self._safety_monitor

    @property
    def safety_monitor_driver(self):
        logger.debug("Observatory.safety_monitor_driver property called")
        return self._safety_monitor_driver

    @property
    def safety_monitor_kwargs(self):
        logger.debug("Observatory.safety_monitor_kwargs property called")
        return self._safety_monitor_kwargs

    @property
    def switch(self):
        logger.debug("Observatory.switch property called")
        return self._switch

    @property
    def switch_driver(self):
        logger.debug("Observatory.switch_driver property called")
        return self._switch_driver

    @property
    def switch_kwargs(self):
        logger.debug("Observatory.switch_kwargs property called")
        return self._switch_kwargs

    @property
    def telescope(self):
        logger.debug("Observatory.telescope property called")
        return self._telescope

    @property
    def telescope_driver(self):
        logger.debug("Observatory.telescope_driver property called")
        return self._telescope_driver

    @property
    def telescope_kwargs(self):
        logger.debug("Observatory.telescope_kwargs property called")
        return self._telescope_kwargs

    @property
    def min_altitude(self):
        logger.debug("Observatory.min_altitude property called")
        return self._min_altitude

    # JW EDIT

    @min_altitude.setter
    def min_altitude(self, value):
        logger.debug(f"Setting min_altitude = {value}")
        try:
            # Check if the value is already a Quantity with unit of degrees
            if isinstance(value, u.Quantity):
                value = value.to(u.deg)
            else:
                # Assume the value is numeric and needs degree units
                value = float(value) * u.deg
            # Ensure value is within physical limits [0, 90] degrees
            value = max(0 * u.deg, min(90 * u.deg, value))
            self._min_altitude = value
            self._config["telescope"]["min_altitude"] = str(
                value.value
            )  # save the numeric part
        except ValueError:
            logger.error(f"Invalid type for min_altitude: {value}")
            raise ValueError(
                "min_altitude must be a number or an astropy Quantity with angle units."
            )

    # @min_altitude.setter
    # def min_altitude(self, value):
    #     logger.debug(f"Observatory.min_altitude = {value} called")
    #     if type(value) is u.Quantity:
    #         self._min_altitude = value
    #     else:
    #         self._min_altitude = (
    #             min(max(float(value), 0), 90)
    #             if value is not None or value != ""
    #             else None
    #         ) * u.deg
    #     self._config["telescope"]["min_altitude"] = (
    #         str(self._min_altitude.to(u.deg).value)
    #         if self._min_altitude is not None
    #         else ""
    #     )

    @property
    def settle_time(self):
        logger.debug("Observatory.settle_time property called")
        return self._settle_time

    @settle_time.setter
    def settle_time(self, value):
        logger.debug(f"Observatory.settle_time = {value} called")
        self._settle_time = (
            max(float(value), 0) if value is not None or value != "" else None
        )
        self._config["telescope"]["settle_time"] = (
            str(self._settle_time) if self._settle_time is not None else ""
        )

    @property
    def autofocus(self):
        logger.debug("Observatory.autofocus property called")
        return self._autofocus

    @property
    def autofocus_driver(self):
        logger.debug("Observatory.autofocus_driver property called")
        return self._autofocus_driver

    @property
    def autofocus_kwargs(self):
        logger.debug("Observatory.autofocus_kwargs property called")
        return self._autofocus_kwargs

    @property
    def slew_rate(self):
        logger.debug("Observatory.slew_rate property called")
        return self._slew_rate

    @slew_rate.setter
    def slew_rate(self, value):
        logger.debug(f"Observatory.slew_rate = {value} called")
        self._slew_rate = float(value) if value is not None or value != "" else None
        self._config["scheduling"]["slew_rate"] = (
            str(self._slew_rate) if self._slew_rate is not None else ""
        )

    @property
    def instrument_reconfig_times(self):
        logger.debug("Observatory.instrument_reconfig_times property called")
        return self._instrument_reconfig_times

    @instrument_reconfig_times.setter
    def instrument_reconfig_times(self, value):
        logger.debug(f"Observatory.instrument_reconfig_times = {value} called")
        self._instrument_reconfig_times = (
            value if value is not None or value != "" else {}
        )
        self._config["scheduling"]["instrument_reconfig_times"] = (
            json.dumps(self._instrument_reconfig_times)
            if self._instrument_reconfig_times is not None
            else "{}"
        )

    @property
    def last_camera_shutter_status(self):
        logger.debug("Observatory.last_camera_shutter_status property called")
        return self._last_camera_shutter_status

    @property
    def current_focus_offset(self):
        logger.debug("Observatory.current_focus_offset property called")
        return self._current_focus_offset

    @property
    def maxim(self):
        logger.debug("Observatory.maxim property called")
        return self._maxim


def _import_driver(driver, kwargs=None):
    """Imports a driver. If the driver is None, returns None. First tries to
    import the driver from the observatory package.

    """

    logger.debug("observatory._import_driver() called")

    if driver is None:
        return None

    try:
        device_class = getattr(observatory, driver)
    except:
        try:
            module_name = kwargs.values()[0].split("/")[-1].split(".")[0]
            spec = importlib.util.spec_from_file_location(module_name, kwargs[0])
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            device_class = getattr(module, driver)

            if len(kwargs) > 1:
                kwargs = kwargs[1:]
            else:
                kwargs = None
        except:
            return None

    if kwargs is None:
        return device_class()
    else:
        return device_class(**kwargs)


def _check_class_inheritance(device_class, device):
    logger.debug("observatory._check_class_inheritance() called")
    if not getattr(observatory, device) in device_class.__bases__:
        raise ObservatoryException(
            "Driver %s does not inherit from the required _abstract classes"
            % device_class
        )
    else:
        logger.debug(
            "Driver %s inherits from the required _abstract classes" % device_class
        )
