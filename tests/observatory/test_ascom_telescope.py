import time

import pytest


def test_destinationsideofpier(device, disconnect):
    assert device.DestinationSideOfPier(12, 45) is not None


def test_findhome(device, disconnect):
    if device.CanFindHome:
        if device.CanUnpark:
            device.Unpark()
        device.FindHome()
        while device.Slewing:
            time.sleep(0.1)
        assert device.AtHome


def test_park(device, disconnect):
    if device.CanPark:
        device.Park()
        while device.Slewing:
            time.sleep(0.1)
        assert device.AtPark


def test_setpark(device, disconnect):
    if device.CanSetPark:
        device.SetPark()


@pytest.mark.skip(
    reason="Synchronous methods are deprecated, not available via Alpaca."
)
def test_slewtoaltaz(device, disconnect):
    if device.CanSlewAltAz:
        device.SlewToAltAz(Altitude=45, Azimuth=180)


def test_slewtoaltazasync(device, disconnect):
    if device.CanSlewAltAzAsync:
        if device.CanUnpark:
            device.Unpark()
        if device.CanSetTracking:
            device.Tracking = False
        device.SlewToAltAzAsync(Altitude=45, Azimuth=90)
        device.AbortSlew()


@pytest.mark.skip(
    reason="Synchronous methods are deprecated, not available via Alpaca."
)
def test_slewtocoordinates(device, disconnect):
    if device.CanSlew:
        if device.CanUnpark:
            device.Unpark()
        device.SlewToCoordinates(device.SiderealTime, device.SiteLatitude)


def test_slew_tocoordinatesasync(device, disconnect):
    if device.CanSlewAsync:
        if device.CanUnpark:
            device.Unpark()
        device.SlewToCoordinatesAsync(device.SiderealTime, device.SiteLatitude)
        device.AbortSlew()


@pytest.mark.skip(
    reason="Synchronous methods are deprecated, not available via Alpaca."
)
def test_slewtotarget(device, disconnect):
    device.TargetDeclination = device.SiteLatitude
    assert device.TargetDeclination == device.SiteLatitude

    t = device.SiderealTime
    device.TargetRightAscension = t
    assert device.TargetRightAscension == t

    if device.CanUnpark:
        device.Unpark()

    device.SlewToTarget()


def test_slewtotargetasync(device, disconnect):
    device.TargetDeclination = device.SiteLatitude
    assert device.TargetDeclination == device.SiteLatitude

    t = device.SiderealTime
    device.TargetRightAscension = t
    assert device.TargetRightAscension == t

    if device.CanUnpark:
        device.Unpark()

    device.SlewToTargetAsync()
    device.AbortSlew()


def test_synctoaltaz(device, disconnect):
    if device.CanSyncAltAz:
        if device.CanSetTracking:
            device.Tracking = False
        device.SyncToAltAz(45, 90)


def test_synctocoordinates(device, disconnect):
    if device.CanSync:
        if device.CanSetTracking:
            device.Tracking = True
        device.SyncToCoordinates(device.SiderealTime, device.SiteLatitude)


def test_synctotarget(device, disconnect):
    if device.CanSync:
        device.TargetDeclination = device.SiteLatitude
        assert device.TargetDeclination == device.SiteLatitude

        t = device.SiderealTime
        device.TargetRightAscension = t
        assert device.TargetRightAscension == t

        if device.CanSetTracking:
            device.Tracking = True

        device.SyncToTarget()


def test_unpark(device, disconnect):
    if device.CanUnpark:
        device.Unpark()
        assert not device.AtPark


def test_alignmentmode(device, disconnect):
    assert device.AlignmentMode is not None


def test_altitude(device, disconnect):
    assert device.Altitude is not None


def test_aperturearea(device, disconnect):
    assert device.ApertureArea is not None


def test_aperturediameter(device, disconnect):
    assert device.ApertureDiameter is not None


def test_azimuth(device, disconnect):
    assert device.Azimuth is not None


def test_declination(device, disconnect):
    assert device.Declination is not None


def test_declinationrate(device, disconnect):
    if device.CanSetDeclinationRate:
        device.DeclinationRate = 1
        assert device.DeclinationRate == 1


def test_doesrefraction(device, disconnect):
    assert device.DoesRefraction is not None
    device.DoesRefraction = True
    assert device.DoesRefraction


def test_equatorialsystem(device, disconnect):
    assert device.EquatorialSystem is not None


def test_focallength(device, disconnect):
    assert device.FocalLength is not None


def test_guideratedeclination(device, disconnect):
    assert device.GuideRateDeclination is not None
    device.GuideRateDeclination = 1
    assert device.GuideRateDeclination == 1


def test_guideraterightascension(device, disconnect):
    assert device.GuideRateRightAscension is not None
    device.GuideRateRightAscension = 1
    assert device.GuideRateRightAscension == 1


def test_ispulseguiding(device, disconnect):
    assert device.IsPulseGuiding is not None


def test_rightascension(device, disconnect):
    assert device.RightAscension is not None


def test_rightascensionrate(device, disconnect):
    if device.CanSetRightAscensionRate:
        device.RightAscensionRate = 1
        assert device.RightAscensionRate == 1


def test_sideofpier(device, disconnect):
    if device.CanSetPierSide:
        assert device.SideOfPier is not None


def test_siteeleveation(device, disconnect):
    assert device.SiteElevation is not None
    device.SiteElevation = 100
    assert device.SiteElevation == 100


def test_sitelongitude(device, disconnect):
    assert device.SiteLongitude is not None
    device.SiteLongitude = 0
    assert device.SiteLongitude == 0


def test_slewsettletime(device, disconnect):
    assert device.SlewSettleTime is not None
    device.SlewSettleTime = 1
    assert device.SlewSettleTime == 1


def test_tracking(device, disconnect):
    if device.CanSetTracking:
        device.Tracking = True
        assert device.Tracking


@pytest.mark.skip(reason="Alpaca implementation issue")
def test_trackingrate(device, disconnect):
    if device.CanSetTracking:
        assert device.TrackingRate is not None
        device.TrackingRate = device.TrackingRates[0]
        assert device.TrackingRate == device.TrackingRates[0]


def test_utcdate(device, disconnect):
    assert device.UTCDate is not None
    device.UTCDate = "2020-01-01T00:00:00"
    assert (
        device.UTCDate.strftime("%Y-%m-%dT%H:%M:%S") == "2020-01-01T00:00:00"
    )
