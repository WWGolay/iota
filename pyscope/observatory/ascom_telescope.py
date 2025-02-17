import logging

from .ascom_device import ASCOMDevice
from .telescope import Telescope

logger = logging.getLogger(__name__)


class ASCOMTelescope(ASCOMDevice, Telescope):
    def __init__(
        self, identifier, alpaca=False, device_number=0, protocol="http"
    ):
        """
        ASCOM implementation of the Telescope base class.

        This class provides an interface for an ASCOM-compatible telescope. Methods include
        slewing the telescope, halting movement, and properties for determining the current
        position and movement state of the telescope.

        Parameters
        ----------
        identifier : `str`
            The unique device identifier. This can be the ProgID for COM devices or the device number for Alpaca devices.
        alpaca : `bool`, default : `False`, optional
            Whether to use the Alpaca protocol, for Alpaca devices. If `False`, the COM protocol is used.
        device_number : `int`, default : 0, optional
            The device number.
        protocol : `str`, default : "http", optional
            The communication protocol to use.
        """
        self.identifier = identifier
        super().__init__(
            identifier,
            alpaca=alpaca,
            device_type=self.__class__.__name__.replace("ASCOM", ""),
            device_number=device_number,
            protocol=protocol,
        )

    def AbortSlew(self):
        logger.debug("ASCOMTelescope.AbortSlew() called")
        self._device.AbortSlew()

    def AxisRates(self, Axis):
        """
        Set of rates at which the telescope may be moved about the specified axis.

        See `MoveAxis`'s description for more information. Should return an empty set
        if `MoveAxis` is not supported.

        Parameters
        ----------
        Axis : `TelescopeAxes <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_TelescopeAxes.htm>`_
            The axis about which the telescope may be moved. See below for ASCOM standard:
                * 0 : Primary axis, Right Ascension or Azimuth.
                * 1 : Secondary axis, Declination or Altitude.
                * 2 : Tertiary axis, imager rotators.

        Returns
        -------
        `IAxisRates <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_IAxisRates.htm>`_
            While it may look intimidating, this return is but an object representing a
            collection of rates, including properties for both the number of rates, and the
            actual rates, and methods for returning an enumerator for the rates, and for
            disposing of the object as a whole.

        Notes
        -----
        Rates must be absolute non-negative values only. Determining direction
        of motion should be done by the application by applying the appropriate
        sign to the rate. This is to not have the driver present a duplicate
        set of positive and negative rates, therefore decluttering.
        """
        logger.debug(f"ASCOMTelescope.AxisRates({Axis}) called")
        return self._device.AxisRates(Axis)

    def CanMoveAxis(self, Axis):
        """
        Whether the telescope can move about the specified axis with `MoveAxis`. (`bool`)

        See `MoveAxis`'s description for more information.

        Parameters
        ----------
        Axis : `TelescopeAxes <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_TelescopeAxes.htm>`_
            The axis about which the telescope may be moved. See below for ASCOM standard:
                * 0 : Primary axis, Right Ascension or Azimuth.
                * 1 : Secondary axis, Declination or Altitude.
                * 2 : Tertiary axis, imager rotators.
        """
        logger.debug(f"ASCOMTelescope.CanMoveAxis({Axis}) called")
        return self._device.CanMoveAxis(Axis)

    def DestinationSideOfPier(self, RightAscension, Declination):
        """
        For German equatorial mounts, prediction of which side of the pier the telescope will be on after slewing to the specified equatorial coordinates at the current instant of time.

        Parameters
        ----------
        RightAscension : `float`
            Right ascension coordinate (hours) of destination, not current, at current instant of time.
        Declination : `float`
            Declination coordinate (degrees) of destination, not current, at current instant of time.

        Returns
        -------
        `PierSide <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_PierSide.htm>`_
            The side of the pier on which the telescope will be after slewing to the specified coordinates. See below for ASCOM standard:
                * 0 : Normal pointing state, mount on East side of pier, looking West.
                * 1 : Through the pole pointing state, mount on West side of pier, looking East.
                * -1 : Unknown or indeterminate.
        """
        logger.debug(
            f"ASCOMTelescope.DestinationSideOfPier({RightAscension}, {Declination}) called"
        )
        return self._device.DestinationSideOfPier(RightAscension, Declination)

    def FindHome(self):
        logger.debug("ASCOMTelescope.FindHome() called")
        try:
            if callable(self._device.FindHome):
                logger.debug("FindHome() is callable and will be executed.")
                self._device.FindHome()
            else:
                logger.debug(
                    "FindHome() is not callable, using 'self._device.FindHome' to find home for the telescope"
                )
                # Handle it as a property if necessary, or simply ignore if no
                # action is required.
                self._device.FindHome
        except Exception as e:
            logger.error(f"Error in executing or accessing FindHome: {e}")

    def MoveAxis(self, Axis, Rate):
        """
        Move the telescope at the given rate about the specified axis.

        The rate is a value between 0.0 and the maximum value returned by `AxisRates`.
        This movement will continue indefinitely until `MoveAxis` is called again with a rate of 0.0,
        at which point the telescope will restore rate to the one set by `Tracking`. Tracking motion
        is disabled during this movement about axis. The method can be called for each axis independently,
        with each axis moving at its own rate.

        Parameters
        ----------
        Axis : `TelescopeAxes <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_TelescopeAxes.htm>`_
            The axis about which the telescope may be moved. See below for ASCOM standard:
                * 0 : Primary axis, Right Ascension or Azimuth.
                * 1 : Secondary axis, Declination or Altitude.
                * 2 : Tertiary axis, imager rotators.
        Rate : `float`
            Rate of motion in degrees per second. Positive values indicate motion in one direction,
            negative values in the opposite direction, and 0.0 stops motion by this method and resumes tracking motion.

        Notes
        -----
        Rate must be within the values returned by `AxisRates`. Note that those values are absolute,
        and the direction of motion is determined by the sign of the rate given here. This sets `Slewing`
        much like `SlewToAltAz` or `SlewToCoordinates` would, and is therefore affected by `AbortSlew`.
        Depending on `Tracking` state, a setting rate of 0.0 will reset the scope to the previous `TrackingRate`,
        or to no movement at all.
        """
        logger.debug(f"ASCOMTelescope.MoveAxis({Axis}, {Rate}) called")
        self._device.MoveAxis(Axis, Rate)

    def Park(self):
        logger.debug("ASCOMTelescope.Park() called")
        # self._device.Park()
        try:
            if callable(self._device.Park):
                logger.debug("SetPark() is callable and will be executed.")
                self._device.Park()
            else:
                logger.debug(
                    "SetPark() is not callable, using 'self._device.Park' to park the telescope"
                )
                # Handle it as a property if necessary, or simply ignore if no
                # action is required.
                self._device.Park
        except Exception as e:
            logger.error(f"Error in executing or accessing SetPark: {e}")

    def PulseGuide(self, Direction, Duration):
        """
        Move the telescope in the specified direction for the specified time.

        Rate at which the telescope moves is set by `GuideRateRightAscension` and `GuideRateDeclination`.
        Depending on driver implementation and the mount's capabilities, these two rates may be tied together.
        For hardware capable of dual-axis movement, the method returns immediately, otherwise it returns only
        after completion of the guide pulse.

        Parameters
        ----------
        Direction : `GuideDirections <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_GuideDirections.htm>`_
            Direction in which to move the telescope. See below for ASCOM standard:
                * 0 : North or up.
                * 1 : South or down.
                * 2 : East or right.
                * 3 : West or left.
        Duration : `int`
            Time in milliseconds for which to pulse the guide. Must be a positive non-zero value.
        """
        logger.debug(
            f"ASCOMTelescope.PulseGuide({Direction}, {Duration}) called"
        )
        self._device.PulseGuide(Direction, Duration)

    def SetPark(self):
        logger.debug("ASCOMTelescope.SetPark() called")
        self._device.SetPark()

    def SlewToAltAz(self, **kwargs):  # pragma: no cover
        """
        Deprecated

        .. deprecated:: 0.1.1
            ASCOM is deprecating this method.
        """
        error_msg = "Altitude or Azimuth not provided (give as Altitude/Alt and Azimuth/Az, case-insensitive)"
        if len(kwargs) < 2:
            logger.error(error_msg)
            raise ValueError(error_msg)
        Azimuth = ["azimuth", "az"]
        Altitude = ["altitude", "alt"]
        for key in kwargs:
            if type(Azimuth) is list and key.lower() in Azimuth:
                Azimuth = kwargs[key]
            elif type(Altitude) is list and key.lower() in Altitude:
                Altitude = kwargs[key]
        if type(Azimuth) is list or type(Altitude) is list:
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.debug(
            f"ASCOMTelescope.SlewToAltAz({Azimuth}, {Altitude}) called"
        )
        self._device.SlewToAltAz(Azimuth, Altitude)

    def SlewToAltAzAsync(self, **kwargs):
        error_msg = "Altitude or Azimuth not provided (give as Altitude/Alt and Azimuth/Az, case-insensitive)"
        if len(kwargs) < 2:
            logger.error(error_msg)
            raise ValueError(error_msg)
        Azimuth = ["azimuth", "az"]
        Altitude = ["altitude", "alt"]
        for key in kwargs:
            if type(Azimuth) is list and key.lower() in Azimuth:
                Azimuth = kwargs[key]
            elif type(Altitude) is list and key.lower() in Altitude:
                Altitude = kwargs[key]
        if type(Azimuth) is list or type(Altitude) is list:
            logger.error(error_msg)
            raise ValueError(error_msg)
        logger.debug(
            f"ASCOMTelescope.SlewToAltAzAsync({Azimuth}, {Altitude}) called"
        )
        self._device.SlewToAltAzAsync(Azimuth, Altitude)

    def SlewToCoordinates(
        self, RightAscension, Declination
    ):  # pragma: no cover
        """
        Deprecated

        .. deprecated:: 0.1.1
            ASCOM is deprecating this method.
        """
        logger.debug(
            f"ASCOMTelescope.SlewToCoordinates({RightAscension}, {Declination}) called"
        )
        self._device.SlewToCoordinates(RightAscension, Declination)

    def SlewToCoordinatesAsync(self, RightAscension, Declination):
        logger.debug(
            f"ASCOMTelescope.SlewToCoordinatesAsync({RightAscension}, {Declination}) called"
        )
        self._device.SlewToCoordinatesAsync(RightAscension, Declination)

    def SlewToTarget(self):  # pragma: no cover
        """
        Deprecated

        .. deprecated:: 0.1.1
            ASCOM is deprecating this method.
        """
        logger.debug("ASCOMTelescope.SlewToTarget() called")
        self._device.SlewToTarget()

    def SlewToTargetAsync(self):
        logger.debug("ASCOMTelescope.SlewToTargetAsync() called")
        self._device.SlewToTargetAsync()

    def SyncToAltAz(self, Azimuth, Altitude):
        logger.debug(
            f"ASCOMTelescope.SyncToAltAz({Azimuth}, {Altitude}) called"
        )
        self._device.SyncToAltAz(Azimuth, Altitude)

    def SyncToCoordinates(self, RightAscension, Declination):
        logger.debug(
            f"ASCOMTelescope.SyncToCoordinates({RightAscension}, {Declination}) called"
        )
        self._device.SyncToCoordinates(RightAscension, Declination)

    def SyncToTarget(self):
        logger.debug("ASCOMTelescope.SyncToTarget() called")
        self._device.SyncToTarget()

    def Unpark(self):
        logger.debug("ASCOMTelescope.Unpark() called")
        self._device.Unpark()

    @property
    def AlignmentMode(self):
        """
        The alignment mode of the telescope. (`AlignmentModes <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_AlignmentModes.htm>`_)

        See below for ASCOM standard:
            * 0 : Altitude-Azimuth alignment.
            * 1 : Polar (equatorial) mount alignment, NOT German.
            * 2 : German equatorial mount alignment.
        """
        logger.debug("ASCOMTelescope.AlignmentMode property accessed")
        return self._device.AlignmentMode

    @property
    def Altitude(self):
        logger.debug("ASCOMTelescope.Altitude property accessed")
        return self._device.Altitude

    @property
    def ApertureArea(self):
        logger.debug("ASCOMTelescope.ApertureArea property accessed")
        return self._device.ApertureArea

    @property
    def ApertureDiameter(self):
        logger.debug("ASCOMTelescope.ApertureDiameter property accessed")
        return self._device.ApertureDiameter

    @property
    def AtHome(self):
        logger.debug("ASCOMTelescope.AtHome property accessed")
        return self._device.AtHome

    @property
    def AtPark(self):
        logger.debug("ASCOMTelescope.AtPark property accessed")
        return self._device.AtPark

    @property
    def Azimuth(self):
        logger.debug("ASCOMTelescope.Azimuth property accessed")
        return self._device.Azimuth

    @property
    def CanFindHome(self):
        logger.debug("ASCOMTelescope.CanFindHome property accessed")
        canHome = self._device.CanFindHome
        # If identifier contains SiTech, then return True
        # This is a workaround for SiTech controllers that do not return CanFindHome
        # but can actually find home
        if self.identifier.find("SiTech") != -1:
            canHome = True
        return canHome

    @property
    def CanPark(self):
        logger.debug("ASCOMTelescope.CanPark property accessed")
        return self._device.CanPark

    def CanPulseGuide(self, Direction):
        logger.debug(f"ASCOMTelescope.CanPulseGuide({Direction}) called")
        return self._device.CanPulseGuide(Direction)

    @property
    def CanSetDeclinationRate(self):
        logger.debug("ASCOMTelescope.CanSetDeclinationRate property accessed")
        return self._device.CanSetDeclinationRate

    @property
    def CanSetGuideRates(self):
        logger.debug("ASCOMTelescope.CanSetGuideRates property accessed")
        return self._device.CanSetGuideRates

    @property
    def CanSetPark(self):
        logger.debug("ASCOMTelescope.CanSetPark property accessed")
        return self._device.CanSetPark

    @property
    def CanSetPierSide(self):
        logger.debug("ASCOMTelescope.CanSetPierSide property accessed")
        return self._device.CanSetPierSide

    @property
    def CanSetRightAscensionRate(self):
        logger.debug(
            "ASCOMTelescope.CanSetRightAscensionRate property accessed"
        )
        return self._device.CanSetRightAscensionRate

    @property
    def CanSetTracking(self):
        logger.debug("ASCOMTelescope.CanSetTracking property accessed")
        return self._device.CanSetTracking

    @property
    def CanSlew(self):  # pragma: no cover
        """
        Deprecated

        .. deprecated:: 0.1.1
            ASCOM is deprecating this property.
        """
        logger.debug("ASCOMTelescope.CanSlew property accessed")
        return self._device.CanSlew

    @property
    def CanSlewAltAz(self):  # pragma: no cover
        """
        Deprecated

        .. deprecated:: 0.1.1
            ASCOM is deprecating this property.
        """
        logger.debug("ASCOMTelescope.CanSlewAltAz property accessed")
        return self._device.CanSlewAltAz

    @property
    def CanSlewAltAzAsync(self):
        logger.debug("ASCOMTelescope.CanSlewAltAzAsync property accessed")
        return self._device.CanSlewAltAzAsync

    @property
    def CanSlewAsync(self):
        logger.debug("ASCOMTelescope.CanSlewAsync property accessed")
        return self._device.CanSlewAsync

    @property
    def CanSync(self):
        logger.debug("ASCOMTelescope.CanSync property accessed")
        return self._device.CanSync

    @property
    def CanSyncAltAz(self):
        logger.debug("ASCOMTelescope.CanSyncAltAz property accessed")
        return self._device.CanSyncAltAz

    @property
    def CanUnpark(self):
        logger.debug("ASCOMTelescope.CanUnpark property accessed")
        return self._device.CanUnpark

    @property
    def Declination(self):
        logger.debug("ASCOMTelescope.Declination property accessed")
        return self._device.Declination

    @property
    def DeclinationRate(self):
        logger.debug("ASCOMTelescope.DeclinationRate property accessed")
        return self._device.DeclinationRate

    @DeclinationRate.setter
    def DeclinationRate(self, value):
        logger.debug(f"ASCOMTelescope.DeclinationRate set to {value}")
        self._device.DeclinationRate = value

    @property
    def DoesRefraction(self):
        logger.debug("ASCOMTelescope.DoesRefraction property accessed")
        return self._device.DoesRefraction

    @DoesRefraction.setter
    def DoesRefraction(self, value):
        logger.debug(f"ASCOMTelescope.DoesRefraction set to {value}")
        self._device.DoesRefraction = value

    @property
    def EquatorialSystem(self):
        """
        Equatorial coordinate system used by the telescope. (`EquatorialCoordinateType <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_EquatorialCoordinateType.htm>`_)

        See below for ASCOM standard:
            * 0 : Custom/unknown equinox and/or reference frame.
            * 1 : Topocentric coordinates. Coordinates at the current date, allowing for annual aberration and precession-nutation. Most common for amateur telescopes.
            * 2 : J2000 equator and equinox. Coordinates at the J2000 epoch, ICRS reference frame. Most common for professional telescopes.
            * 3 : J2050 equator and equinox. Coordinates at the J2050 epoch, ICRS reference frame.
            * 4 : B1950 equinox. Coordinates at the B1950 epoch, FK4 reference frame.
        """
        logger.debug("ASCOMTelescope.EquatorialSystem property accessed")
        return self._device.EquatorialSystem

    @property
    def FocalLength(self):
        logger.debug("ASCOMTelescope.FocalLength property accessed")
        return self._device.FocalLength

    @property
    def GuideRateDeclination(self):
        logger.debug("ASCOMTelescope.GuideRateDeclination property accessed")
        return self._device.GuideRateDeclination

    @GuideRateDeclination.setter
    def GuideRateDeclination(self, value):
        logger.debug(f"ASCOMTelescope.GuideRateDeclination set to {value}")
        self._device.GuideRateDeclination = value

    @property
    def GuideRateRightAscension(self):
        logger.debug(
            "ASCOMTelescope.GuideRateRightAscension property accessed"
        )
        return self._device.GuideRateRightAscension

    @GuideRateRightAscension.setter
    def GuideRateRightAscension(self, value):
        logger.debug(f"ASCOMTelescope.GuideRateRightAscension set to {value}")
        self._device.GuideRateRightAscension = value

    @property
    def IsPulseGuiding(self):
        logger.debug("ASCOMTelescope.IsPulseGuiding property accessed")
        return self._device.IsPulseGuiding

    @property
    def RightAscension(self):
        logger.debug("ASCOMTelescope.RightAscension property accessed")
        return self._device.RightAscension

    @property
    def RightAscensionRate(self):
        logger.debug("ASCOMTelescope.RightAscensionRate property accessed")
        return self._device.RightAscensionRate

    @RightAscensionRate.setter
    def RightAscensionRate(self, value):
        logger.debug(f"ASCOMTelescope.RightAscensionRate set to {value}")
        self._device.RightAscensionRate = value

    @property
    def SideOfPier(self):
        """
        The pointing state of the mount. (`PierSide <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_PierSide.htm>`_)

        See below for ASCOM standard:
            * 0 : Normal pointing state, mount on East side of pier, looking West.
            * 1 : Through the pole pointing state, mount on West side of pier, looking East.
            * -1 : Unknown or indeterminate.

        .. warning::
            The name of this property is misleading and does not reflect the true meaning of the property.
            The name will not change out of preservation of compatibility.
            For more information, see the 'Remarks' section of `this page <https://ascom-standards.org/Help/Developer/html/P_ASCOM_DeviceInterface_ITelescopeV3_SideOfPier.htm>`_.
        """
        logger.debug("ASCOMTelescope.SideOfPier property accessed")
        return self._device.SideOfPier

    @SideOfPier.setter
    def SideOfPier(self, value):
        logger.debug(f"ASCOMTelescope.SideOfPier set to {value}")
        self._device.SideOfPier = value

    @property
    def SiderealTime(self):
        logger.debug("ASCOMTelescope.SiderealTime property accessed")
        return self._device.SiderealTime

    @property
    def SiteElevation(self):
        logger.debug("ASCOMTelescope.SiteElevation property accessed")
        return self._device.SiteElevation

    @SiteElevation.setter
    def SiteElevation(self, value):
        logger.debug(f"ASCOMTelescope.SiteElevation set to {value}")
        self._device.SiteElevation = value

    @property
    def SiteLatitude(self):
        logger.debug("ASCOMTelescope.SiteLatitude property accessed")
        return self._device.SiteLatitude

    @SiteLatitude.setter
    def SiteLatitude(self, value):
        logger.debug(f"ASCOMTelescope.SiteLatitude set to {value}")
        self._device.SiteLatitude = value

    @property
    def SiteLongitude(self):
        logger.debug("ASCOMTelescope.SiteLongitude property accessed")
        return self._device.SiteLongitude

    @SiteLongitude.setter
    def SiteLongitude(self, value):
        logger.debug(f"ASCOMTelescope.SiteLongitude set to {value}")
        self._device.SiteLongitude = value

    @property
    def Slewing(self):
        logger.debug("ASCOMTelescope.Slewing property accessed")
        return self._device.Slewing

    @property
    def SlewSettleTime(self):
        logger.debug("ASCOMTelescope.SlewSettleTime property accessed")
        return self._device.SlewSettleTime

    @SlewSettleTime.setter
    def SlewSettleTime(self, value):
        logger.debug(f"ASCOMTelescope.SlewSettleTime set to {value}")
        self._device.SlewSettleTime = value

    @property
    def TargetDeclination(self):
        logger.debug("ASCOMTelescope.TargetDeclination property accessed")
        return self._device.TargetDeclination

    @TargetDeclination.setter
    def TargetDeclination(self, value):
        logger.debug(f"ASCOMTelescope.TargetDeclination set to {value}")
        self._device.TargetDeclination = value

    @property
    def TargetRightAscension(self):
        logger.debug("ASCOMTelescope.TargetRightAscension property accessed")
        return self._device.TargetRightAscension

    @TargetRightAscension.setter
    def TargetRightAscension(self, value):
        logger.debug(f"ASCOMTelescope.TargetRightAscension set to {value}")
        self._device.TargetRightAscension = value

    @property
    def Tracking(self):
        logger.debug("ASCOMTelescope.Tracking property accessed")
        return self._device.Tracking

    @Tracking.setter
    def Tracking(self, value):
        logger.debug(f"ASCOMTelescope.Tracking set to {value}")
        self._device.Tracking = value

    @property
    def TrackingRate(self):
        """
        Current tracking rate of the telescope's sidereal drive. (`DriveRates <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_DriveRates.htm>`_)

        Supported rates are contained in `TrackingRates`, and the property's rate
        is guaranteed to be one of those.
        If the mount's current tracking rate cannot be read, the driver should force
        and report a default rate on connection.
        In this circumstance, a default of `Sidereal` rate is preferred.

        See below for ASCOM standard:
            * 0 : Sidereal tracking, 15.041 arcseconds per second.
            * 1 : Lunar tracking, 14.685 arcseconds per second.
            * 2 : Solar tracking, 15.0 arcseconds per second.
            * 3 : King tracking, 15.0369 arcseconds per second.
        """
        logger.debug("ASCOMTelescope.TrackingRate property accessed")
        return self._device.TrackingRate

    @TrackingRate.setter
    def TrackingRate(self, value):
        logger.debug(f"ASCOMTelescope.TrackingRate set to {value}")
        self._device.TrackingRate = value

    @property
    def TrackingRates(self):
        """
        Collection of supported tracking rates for the telescope's sidereal drive. (`TrackingRates <https://ascom-standards.org/Help/Developer/html/T_ASCOM_DeviceInterface_ITrackingRates.htm>`_)

        This collection contains all supported tracking rates. At a minimum, it will contain
        an item for the default `Sidereal` rate. The collection is an iterable, and includes
        properties for the number of rates, and the actual rates, and methods for returning
        an enumerator for the rates, and for disposing of the object as a whole.

        See below for ASCOM standard expected collection:
            * 0 : Sidereal tracking, 15.041 arcseconds per second.
            * 1 : Lunar tracking, 14.685 arcseconds per second.
            * 2 : Solar tracking, 15.0 arcseconds per second.
            * 3 : King tracking, 15.0369 arcseconds per second
        """
        logger.debug("ASCOMTelescope.TrackingRates property accessed")
        return self._device.TrackingRates

    @property
    def UTCDate(self):
        logger.debug("ASCOMTelescope.UTCDate property accessed")
        return self._device.UTCDate

    @UTCDate.setter
    def UTCDate(self, value):
        logger.debug(f"ASCOMTelescope.UTCDate set to {value}")
        self._device.UTCDate = value
