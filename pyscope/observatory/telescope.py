from abc import ABC, abstractmethod

from ..utils._docstring_inheritee import _DocstringInheritee


class Telescope(ABC, metaclass=_DocstringInheritee):
    @abstractmethod
    def __init__(self, *args, **kwargs):
        """
        Abstract base class for a telescope device.

        This class defines the interface for a telescope device, including methods for
        slewing the telescope, halting movement, and properties for determining the current
        position and movement state of the telescope. Subclasses must implement the abstract
        methods and properties in this class.

        Parameters
        ----------
        *args : `tuple`
            Variable length argument list.
        **kwargs : `dict`
            Arbitrary keyword arguments.
        """
        pass

    @abstractmethod
    def AbortSlew(self):
        """
        Immediately stop any movement of the telescope due to any of the SlewTo*** calls.

        Does nothing if the telescope is not slewing. Tracking will return to its pre-slew state.
        """
        pass

    @abstractmethod
    def AxisRates(self, Axis):
        """
        Set of rates at which the telescope may be moved about the specified axis.

        See `MoveAxis`'s description for more information. Should return an empty set
        if `MoveAxis` is not supported.

        Parameters
        ----------
        Axis : `enum`
            The axis about which the telescope may be moved. See below for example values:
                * 0 : Primary axis, usually corresponding to Right Ascension or Azimuth.
                * 1 : Secondary axis, usually corresponding to Declination or Altitude.
                * 2 : Tertiary axis, usually corresponding to imager rotators.

        Returns
        -------
        `object`
            This object should be an iterable collection, including properties for both
            the number of rates, and the actual rates, and methods for returning an
            enumerator for the rates, and for disposing of the object as a whole.

        Notes
        -----
        Rates must be absolute non-negative values only. Determining direction
        of motion should be done by the application by applying the appropriate
        sign to the rate. This is to not have the driver present a duplicate
        set of positive and negative rates, therefore decluttering.
        """
        pass

    @abstractmethod
    def CanMoveAxis(self, Axis):
        """
        Whether the telescope can move about the specified axis with `MoveAxis`. (`bool`)

        See `MoveAxis`'s description for more information.

        Parameters
        ----------
        Axis : `enum`
            The axis about which the telescope may be moved. See below for example values:
                * 0 : Primary axis, usually corresponding to Right Ascension or Azimuth.
                * 1 : Secondary axis, usually corresponding to Declination or Altitude.
                * 2 : Tertiary axis, usually corresponding to imager rotators.
        """
        pass

    @abstractmethod
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
        `enum`
            The side of the pier on which the telescope will be after slewing to the specified equatorial coordinates at the current instant of time. See below for example values:
                * 0 : Normal pointing state, mount on East side of pier, looking West.
                * 1 : Through the pole pointing state, mount on West side of pier, looking East.
                * -1 : Unknown or indeterminate.
        """
        pass

    @abstractmethod
    def FindHome(self):
        """
        Synchronously locate the telescope's home position.

        Returns only once the home position has been located. After locating,
        `AtHome` will set to `True`.
        """
        pass

    @abstractmethod
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
        Axis : `enum`
            The axis about which the telescope may be moved. See below for example values:
                * 0 : Primary axis, usually corresponding to Right Ascension or Azimuth.
                * 1 : Secondary axis, usually corresponding to Declination or Altitude.
                * 2 : Tertiary axis, usually corresponding to imager rotators.
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
        pass

    @abstractmethod
    def Park(self):
        """
        Moves the telescope to the park position.

        To achieve this, it stops all motion (alternatively just restrict it to a small safe range),
        park, then set `AtPark` to `True`. Calling it with `AtPark` already `True` is safe to do.
        """
        pass

    @abstractmethod
    def PulseGuide(self, Direction, Duration):
        """
        Move the telescope in the specified direction for the specified time.

        Rate at which the telescope moves is set by `GuideRateRightAscension` and `GuideRateDeclination`.
        Depending on driver implementation and the mount's capabilities, these two rates may be tied together.
        For hardware capable of dual-axis movement, the method returns immediately, otherwise it returns only
        after completion of the guide pulse.

        Parameters
        ----------
        Direction : `enum`
            Direction in which to move the telescope. See below for example values:
                * 0 : North or up.
                * 1 : South or down.
                * 2 : East or right.
                * 3 : West or left.
        Duration : `int`
            Time in milliseconds for which to pulse the guide. Must be a positive non-zero value.
        """
        pass

    @abstractmethod
    def SetPark(self):
        """Sets the telescope's park position to the current position."""
        pass

    @abstractmethod
    def SlewToAltAz(self, **kwargs):
        """
        Move the telescope to the specified Alt/Az coordinates.

        Slew may fail if target is beyond limits imposed within the driver component. These limits
        could be mechanical constraints by the mount or instruments, safety restrictions from the
        building or dome enclosure, etc.
        `TargetRightAscension` and `TargetDeclination` will be unchanged by this method.

        Implementers should use keyword arguments for the Alt/Az coordinates, detect the keys, and use the values accordingly.
        This is to allow explicit naming of the coordinates, as well as to separate future implementations from the ASCOM implementation,
        where the method unintuitively expects the arguments in Azimuth-Altitude order, despite the method name.

        Parameters
        ----------
        kwargs : `dict`
            Keyword arguments for the Alt/Az coordinates. Azimuth should be in degrees, North-referenced, CW. Altitude should be in degrees.
        """
        pass

    @abstractmethod
    def SlewToAltAzAsync(self, **kwargs):
        """
        Move the telescope to the specified Alt/Az coordinates asynchronously.

        Method should only be implemented if the telescope is capable of reading `Altitude`, `Azimuth`, `RightAscension`, and `Declination`
        while slewing. Returns immediately after starting the slew.
        Slew may fail if target is beyond limits imposed within the driver component. These limits
        could be mechanical constraints by the mount or instruments, safety restrictions from the
        building or dome enclosure, etc.
        `TargetRightAscension` and `TargetDeclination` will be unchanged by this method.

        Implementers should use keyword arguments for the Alt/Az coordinates, detect the keys, and use the values accordingly.
        This is to allow explicit naming of the coordinates, as well as to separate future implementations from the ASCOM implementation,
        where the method unintuitively expects the arguments in Azimuth-Altitude order, despite the method name.

        Parameters
        ----------
        kwargs : `dict`
            Keyword arguments for the Alt/Az coordinates. Azimuth should be in degrees, North-referenced, CW. Altitude should be in degrees.
        """
        pass

    @abstractmethod
    def SlewToCoordinates(self, RightAscension, Declination):
        """
        Move the telescope to the specified equatorial coordinates.

        Slew may fail if target is beyond limits imposed within the driver component. These limits
        could be mechanical constraints by the mount or instruments, safety restrictions from the
        building or dome enclosure, etc.
        `TargetRightAscension` and `TargetDeclination` will set to the specified coordinates, irrelevant of
        whether the slew was successful.

        Parameters
        ----------
        RightAscension : `float`
            Right ascension coordinate in hours.
        Declination : `float`
            Declination coordinate in degrees.
        """
        pass

    @abstractmethod
    def SlewToCoordinatesAsync(self, RightAscension, Declination):
        """
        Move the telescope to the specified equatorial coordinates asynchronously.

        Returns immediately after starting the slew. Slew may fail if target is beyond limits imposed within the driver component.
        These limits could be mechanical constraints by the mount or instruments, safety restrictions from the building or dome enclosure, etc.
        `TargetRightAscension` and `TargetDeclination` will set to the specified coordinates, irrelevant of whether the slew was successful.

        Parameters
        ----------
        RightAscension : `float`
            Right ascension coordinate in hours.
        Declination : `float`
            Declination coordinate in degrees.
        """
        pass

    @abstractmethod
    def SlewToTarget(self):
        """
        Move the telescope to the `TargetRightAscension` and `TargetDeclination` coordinates.

        Slew may fail if target is beyond limits imposed within the driver component. These limits
        could be mechanical constraints by the mount or instruments, safety restrictions from the
        building or dome enclosure, etc.
        """
        pass

    @abstractmethod
    def SlewToTargetAsync(self):
        """
        Move the telescope to the `TargetRightAscension` and `TargetDeclination` coordinates asynchronously.

        Returns immediately after starting the slew. Slew may fail if target is beyond limits imposed within the driver component.
        These limits could be mechanical constraints by the mount or instruments, safety restrictions from the building or dome enclosure, etc.
        """
        pass

    @abstractmethod
    def SyncToAltAz(self, Azimuth, Altitude):
        """
        Synchronizes the telescope's current local horizontal coordinates to the specified Alt/Az coordinates.

        Parameters
        ----------
        Azimuth : `float`
            Azimuth coordinate in degrees, North-referenced, CW.
        Altitude : `float`
            Altitude coordinate in degrees.
        """
        pass

    @abstractmethod
    def SyncToCoordinates(self, RightAscension, Declination):
        """
        Synchronizes the telescope's current equatorial coordinates to the specified RA/Dec coordinates.

        Parameters
        ----------
        RightAscension : `float`
            Right ascension coordinate in hours.
        Declination : `float`
            Declination coordinate in degrees.
        """
        pass

    @abstractmethod
    def SyncToTarget(self):
        """
        Synchronizes the telescope's current equatorial coordinates to the `TargetRightAscension` and `TargetDeclination` coordinates.

        This method should only be used to improve the pointing accuracy of the telescope for positions close
        to the position at which the sync is done, since Sync is mount-dependent.
        """
        pass

    @abstractmethod
    def Unpark(self):
        """Takes the telescope out of the `Parked` state."""
        pass

    @property
    @abstractmethod
    def AlignmentMode(self):
        """
        The alignment mode of the telescope. (`enum`)

        See below for example values:
            * 0 : Altitude-Azimuth alignment.
            * 1 : Polar (equatorial) mount alignment, NOT German.
            * 2 : German equatorial mount alignment.
        """
        pass

    @AlignmentMode.setter
    @abstractmethod
    def AlignmentMode(self, value):
        pass

    @property
    @abstractmethod
    def Altitude(self):
        """Altitude above the horizon of the telescope's current position in degrees. (`float`)"""
        pass

    @property
    @abstractmethod
    def ApertureArea(self):
        """Area of the telescope's aperture in square meters, accounting for obstructions. (`float`)"""
        pass

    @property
    @abstractmethod
    def ApertureDiameter(self):
        """Effective diameter of the telescope's aperture in meters. (`float`)"""
        pass

    @property
    @abstractmethod
    def AtHome(self):
        """
        Whether the telescope is at the home position. (`bool`)

        Only `True` after a successful `FindHome` call, and `False` after any slewing operation.
        Alternatively, `False` if the telescope is not capable of homing.
        """
        pass

    @property
    @abstractmethod
    def AtPark(self):
        """
        Whether the telescope is in the `Parked` state. (`bool`)

        See `Park` and `Unpark` for more information.
        Setting to `True` or `False` should only be done by those methods respectively.
        While `True`, no movement commands should be accepted except `Unpark`, and an attempt
        to do so should raise an error.
        """
        pass

    @property
    @abstractmethod
    def Azimuth(self):
        """Azimuth of the telescope's current position in degrees, North-referenced, CW. (`float`)"""
        pass

    @property
    @abstractmethod
    def CanFindHome(self):
        """Whether the telescope is capable of finding its home position with `FindHome`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanPark(self):
        """Whether the telescope is capable of parking with `Park`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanPulseGuide(self):
        """Whether the telescope is capable of pulse guiding with `PulseGuide`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanSetDeclinationRate(self):
        """Whether the telescope is capable of setting the declination rate with `DeclinationRate` for offset tracking. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanSetGuideRates(self):
        """Whether the telescope is capable of setting the guide rates with `GuideRateRightAscension` and `GuideRateDeclination`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanSetPark(self):
        """Whether the telescope is capable of setting the park position with `SetPark`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanSetPierSide(self):
        """
        Whether the telescope is capable of setting the side of the pier with `SideOfPier`, i.e. the mount can be forced to flip. (`bool`)

        This is only relevant for German equatorial mounts, as non-Germans do not have to be flipped
        and should therefore have `CansetPierSide` `False`.
        """
        pass

    @property
    @abstractmethod
    def CanSetRightAscensionRate(self):
        """Whether the telescope is capable of setting the right ascension rate with `RightAscensionRate` for offset tracking. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanSetTracking(self):
        """Whether the telescope is capable of setting the tracking state with `Tracking`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanSlew(self):
        """
        Whether the telescope is capable of slewing with `SlewToCoordinates`, or `SlewToTarget`. (`bool`)

        A `True` only guarantees that the synchronous slews are possible.
        Asynchronous slew capabilies are determined by `CanSlewAsync`.
        """
        pass

    @property
    @abstractmethod
    def CanSlewAltAz(self):
        """
        Whether the telescope is capable of slewing to Alt/Az coordinates with `SlewToAltAz`. (`bool`)

        A `True` only guarantees that the synchronous local horizontal slews are possible.
        Asynchronous slew capabilies are determined by `CanSlewAltAzAsync`.
        """
        pass

    @property
    @abstractmethod
    def CanSlewAltAzAsync(self):
        """
        Whether the telescope is capable of slewing to Alt/Az coordinates asynchronously with `SlewToAltAzAsync`. (`bool`)

        A `True` also guarantees that the synchronous local horizontal slews are possible.
        """
        pass

    @property
    @abstractmethod
    def CanSlewAsync(self):
        """
        Whether the telescope is capable of slewing asynchronously with `SlewToCoordinatesAsync`, `SlewToAltAzAsync`, or `SlewToTargetAsync`. (`bool`)

        A `True` also guarantees that the synchronous slews are possible.
        """
        pass

    @property
    @abstractmethod
    def CanSync(self):
        """Whether the telescope is capable of syncing with `SyncToCoordinates` or `SyncToTarget`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanSyncAltAz(self):
        """Whether the telescope is capable of syncing to Alt/Az coordinates with `SyncToAltAz`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def CanUnpark(self):
        """Whether the telescope is capable of unparking with `Unpark`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def Declination(self):
        """Declination of the telescope's current position, in the coordinate system given by `EquatorialSystem`, in degrees. (`float`)"""
        pass

    @Declination.setter
    @abstractmethod
    def Declination(self, value):
        pass

    @property
    @abstractmethod
    def DeclinationRate(self):
        """
        Declination tracking rate in arcseconds per second. (`float`)

        This, in conjunction with `RightAscensionRate`, is primarily used for offset tracking,
        tracking objects that move relatively slowly against the equatorial coordinate system.
        The supported range is telescope-dependent, but it can be expected to be a range
        sufficient for guiding error corrections.
        """
        pass

    @DeclinationRate.setter
    @abstractmethod
    def DeclinationRate(self, value):
        pass

    @property
    @abstractmethod
    def DoesRefraction(self):
        """Whether the telescope applies atmospheric refraction to coordinates. (`bool`)"""
        pass

    @DoesRefraction.setter
    @abstractmethod
    def DoesRefraction(self, value):
        pass

    @property
    @abstractmethod
    def EquatorialSystem(self):
        """
        Equatorial coordinate system used by the telescope. (`enum`)

        See below for example values:
            * 0 : Custom/unknown equinox and/or reference frame.
            * 1 : Topocentric coordinates. Coordinates at the current date, allowing for annual aberration and precession-nutation. Most common for amateur telescopes.
            * 2 : J2000 equator and equinox. Coordinates at the J2000 epoch, ICRS reference frame. Most common for professional telescopes.
            * 3 : J2050 equator and equinox. Coordinates at the J2050 epoch, ICRS reference frame.
            * 4 : B1950 equinox. Coordinates at the B1950 epoch, FK4 reference frame.
        """
        pass

    @property
    @abstractmethod
    def FocalLength(self):
        """
        Focal length of the telescope in meters. (`float`)

        May be used by clients to calculate the field of view and plate scale of the telescope
        in combination with detector pixel size and geometry.
        """
        pass

    @property
    @abstractmethod
    def GuideRateDeclination(self):
        """
        Current declination movement rate offset in degrees per second. (`float`)

        This is the rate for both hardware guiding and the `PulseGuide` method.
        The supported range is telescope-dependent, but it can be expected to be a range
        sufficient for guiding error corrections.
        If the telescope is incapable of separate guide rates for RA and Dec, this property
        and `GuideRateRightAscension` may be tied together; changing one property will change the other.
        Mounts must start up with a default rate, and this property must return that rate until changed.
        """
        pass

    @GuideRateDeclination.setter
    @abstractmethod
    def GuideRateDeclination(self, value):
        pass

    @property
    @abstractmethod
    def GuideRateRightAscension(self):
        """
        Current right ascension movement rate offset in degrees per second. (`float`)

        This is the rate for both hardware guiding and the `PulseGuide` method.
        The supported range is telescope-dependent, but it can be expected to be a range
        sufficient for guiding error corrections.
        If the telescope is incapable of separate guide rates for RA and Dec, this property
        and `GuideRateDeclination` may be tied together; changing one property will change the other.
        Mounts must start up with a default rate, and this property must return that rate until changed.
        """
        pass

    @GuideRateRightAscension.setter
    @abstractmethod
    def GuideRateRightAscension(self, value):
        pass

    @property
    @abstractmethod
    def IsPulseGuiding(self):
        """Whether the telescope is currently pulse guiding using `PulseGuide`. (`bool`)"""
        pass

    @property
    @abstractmethod
    def RightAscension(self):
        """Right ascension of the telescope's current position, in the coordinate system given by `EquatorialSystem`, in hours. (`float`)"""
        pass

    @property
    @abstractmethod
    def RightAscensionRate(self):
        """
        Right ascension tracking rate in seconds per sidereal second. (`float`)

        This, in conjunction with `DeclinationRate`, is primarily used for offset tracking,
        tracking objects that move relatively slowly against the equatorial coordinate system.
        The supported range is telescope-dependent, but it can be expected to be a range
        sufficient for guiding error corrections.

        Notes
        -----
        To convet to sidereal seconds per UTC second, multiply by 0.9972695677.
        """
        pass

    @RightAscensionRate.setter
    @abstractmethod
    def RightAscensionRate(self, value):
        pass

    @property
    @abstractmethod
    def SideOfPier(self):
        """
        The pointing state of the mount. (`enum`)

        See below for example values:
            * 0 : Normal pointing state, mount on East side of pier, looking West.
            * 1 : Through the pole pointing state, mount on West side of pier, looking East.
            * -1 : Unknown or indeterminate.

        .. warning::
            The name of this property is misleading and does not reflect the true meaning of the property.
            The name will not change out of preservation of compatibility.
            For more information, see the 'Remarks' section of `this page <https://ascom-standards.org/Help/Developer/html/P_ASCOM_DeviceInterface_ITelescopeV3_SideOfPier.htm>`_.
        """
        pass

    @SideOfPier.setter
    @abstractmethod
    def SideOfPier(self, value):
        pass

    @property
    @abstractmethod
    def SiderealTime(self):
        """
        Local apparent sidereal time from the telescope's internal clock in hours. (`float`)

        If the telesope has no sidereal time capability, this property should be calculated from the system
        clock by the driver.
        """
        pass

    @property
    @abstractmethod
    def SiteElevation(self):
        """Elevation of the telescope's site above sea level in meters. (`float`)"""
        pass

    @SiteElevation.setter
    @abstractmethod
    def SiteElevation(self, value):
        pass

    @property
    @abstractmethod
    def SiteLatitude(self):
        """Latitude (geodetic) of the telescope's site in degrees. (`float`)"""
        pass

    @SiteLatitude.setter
    @abstractmethod
    def SiteLatitude(self, value):
        pass

    @property
    @abstractmethod
    def SiteLongitude(self):
        """Longitude (geodetic) of the telescope's site in degrees. (`float`)"""
        pass

    @property
    @abstractmethod
    def Slewing(self):
        """
        Whether the telescope is currently slewing due to one of the Slew methods or `MoveAxis`. (`bool`)

        Telescopes incapable of asynchronous slewing will always have this property be `False`.
        Slewing for the purpose of this property excludes motion by sidereal tracking, pulse guiding,
        `RightAscensionRate`, and `DeclinationRate`.
        Only Slew commands, flipping due to `SideOfPier`, and `MoveAxis` should set this property to `True`.
        """
        pass

    @property
    @abstractmethod
    def SlewSettleTime(self):
        """
        A set post-slew settling time in seconds. (`int`)

        This adds additional time to the end of all slew operations.
        In practice, slew methods will not return, and `Slewing` will not be `False`, until the
        operation has ended plus this time has elapsed.
        """
        pass

    @SlewSettleTime.setter
    @abstractmethod
    def SlewSettleTime(self, value):
        pass

    @property
    @abstractmethod
    def TargetDeclination(self):
        """Declination coordinate in degrees of the telescope's current slew or sync target. (`float`)"""
        pass

    @TargetDeclination.setter
    @abstractmethod
    def TargetDeclination(self, value):
        pass

    @property
    @abstractmethod
    def TargetRightAscension(self):
        """Right ascension coordinate in hours of the telescope's current slew or sync target. (`float`)"""
        pass

    @TargetRightAscension.setter
    @abstractmethod
    def TargetRightAscension(self, value):
        pass

    @property
    @abstractmethod
    def Tracking(self):
        """
        State of the telescope's sidereal tracking drive. (`bool`)

        Changing of this property will turn sidereal drive on and off.
        Some telescopes may not support changing of this property, and thus
        may not support turning tracking on and off. See `CanSetTracking`.
        """
        pass

    @Tracking.setter
    @abstractmethod
    def Tracking(self, value):
        pass

    @property
    @abstractmethod
    def TrackingRate(self):
        """
        Current tracking rate of the telescope's sidereal drive. (`enum`)

        Supported rates are contained in `TrackingRates`, and the property's rate
        is guaranteed to be one of those.
        If the mount's current tracking rate cannot be read, the driver should force
        and report a default rate on connection.
        In this circumstance, a default of `Sidereal` rate is preferred.

        See below for example values:
            * 0 : Sidereal tracking, 15.041 arcseconds per second.
            * 1 : Lunar tracking, 14.685 arcseconds per second.
            * 2 : Solar tracking, 15.0 arcseconds per second.
            * 3 : King tracking, 15.0369 arcseconds per second.
        """
        pass

    @TrackingRate.setter
    @abstractmethod
    def TrackingRate(self, value):
        pass

    @property
    @abstractmethod
    def TrackingRates(self):
        """
        Collection of supported tracking rates for the telescope's sidereal drive. (`object`)

        This collection should contain all supported tracking rates. At a minimum, it should contain
        an item for the default `Sidereal` rate. The collection should be an iterable, and should
        include properties for the number of rates, and the actual rates, and methods for returning
        an enumerator for the rates, and for disposing of the object as a whole.

        See below for an example collection:
            * 0 : Sidereal tracking, 15.041 arcseconds per second.
            * 1 : Lunar tracking, 14.685 arcseconds per second.
            * 2 : Solar tracking, 15.0 arcseconds per second.
            * 3 : King tracking, 15.0369 arcseconds per second.
        """
        pass

    @property
    @abstractmethod
    def UTCDate(self):
        """
        UTC date and time of the telescope's internal clock. (`datetime`)

        If the telescope has no UTC time capability, this property should be calculated from the system
        clock by the driver.
        If the telescope does have UTC measuring capability, changing of its internal UTC clock is permitted,
        for instance for allowing clients to adjust for accuracy.

        .. warning::
            If the telescope has no UTC time capability, do NOT under any circumstances implement the property
            to be writeable, as it would change the system clock.
        """
        pass

    @UTCDate.setter
    @abstractmethod
    def UTCDate(self, value):
        pass
