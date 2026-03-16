"""
Sun position and golden hour analysis for peak_finder.
Uses the astral library (v3+).
"""

import datetime
from typing import Optional

from astral import LocationInfo, Observer
from astral.sun import sun, azimuth
from rich import print as rprint

# Try to import timezonefinder for accurate local time zone lookup
try:
    from timezonefinder import TimezoneFinder
    import zoneinfo

    _TF = TimezoneFinder()

    def _get_tzinfo(lat: float, lon: float):
        tz_name = _TF.timezone_at(lat=lat, lng=lon)
        if tz_name:
            return zoneinfo.ZoneInfo(tz_name)
        return datetime.timezone.utc

except ImportError:
    _TF = None

    def _get_tzinfo(lat: float, lon: float):  # type: ignore[misc]
        return datetime.timezone.utc


MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _make_observer(lat: float, lon: float) -> Observer:
    """Create an astral Observer for the given coordinates."""
    return Observer(latitude=lat, longitude=lon)


def get_sun_info(
    lat: float,
    lon: float,
    query_date: Optional[datetime.date] = None,
) -> dict:
    """
    Compute sunrise, sunset, and golden hour information for a location.

    Args:
        lat:        Latitude in decimal degrees.
        lon:        Longitude in decimal degrees.
        query_date: Date to compute sun positions for (defaults to today).

    Returns:
        Dict with keys:
            sunrise_utc                  – datetime (UTC)
            sunset_utc                   – datetime (UTC)
            golden_hour_morning_start    – datetime (UTC), 30 min after sunrise
            golden_hour_morning_end      – datetime (UTC), 60 min after sunrise
            golden_hour_evening_start    – datetime (UTC), 60 min before sunset
            golden_hour_evening_end      – datetime (UTC), 30 min before sunset
            golden_hour_morning_azimuth  – sun azimuth at morning golden hour midpoint (degrees)
            golden_hour_evening_azimuth  – sun azimuth at evening golden hour midpoint (degrees)
            best_months                  – string describing best photography months
        On failure returns a dict with None values and description="unavailable".
    """
    unavailable = {
        "sunrise_utc": None,
        "sunset_utc": None,
        "golden_hour_morning_start": None,
        "golden_hour_morning_end": None,
        "golden_hour_evening_start": None,
        "golden_hour_evening_end": None,
        "golden_hour_morning_azimuth": None,
        "golden_hour_evening_azimuth": None,
        "best_months": "unavailable",
    }

    if query_date is None:
        query_date = datetime.date.today()

    try:
        observer = _make_observer(lat, lon)
        s = sun(observer, date=query_date, tzinfo=datetime.timezone.utc)

        sunrise_utc: datetime.datetime = s["sunrise"]
        sunset_utc: datetime.datetime = s["sunset"]

        # Golden hour: 30–60 min after sunrise and 30–60 min before sunset
        gh_morning_start = sunrise_utc + datetime.timedelta(minutes=30)
        gh_morning_end = sunrise_utc + datetime.timedelta(minutes=60)
        gh_evening_start = sunset_utc - datetime.timedelta(minutes=60)
        gh_evening_end = sunset_utc - datetime.timedelta(minutes=30)

        # Sun azimuth at midpoint of each golden hour window
        morning_mid = sunrise_utc + datetime.timedelta(minutes=45)
        evening_mid = sunset_utc - datetime.timedelta(minutes=45)

        morning_az = azimuth(observer, morning_mid)
        evening_az = azimuth(observer, evening_mid)

        # Best months heuristic
        best_months = "May–September" if lat >= 0 else "November–March"

        return {
            "sunrise_utc": sunrise_utc,
            "sunset_utc": sunset_utc,
            "golden_hour_morning_start": gh_morning_start,
            "golden_hour_morning_end": gh_morning_end,
            "golden_hour_evening_start": gh_evening_start,
            "golden_hour_evening_end": gh_evening_end,
            "golden_hour_morning_azimuth": round(morning_az, 1),
            "golden_hour_evening_azimuth": round(evening_az, 1),
            "best_months": best_months,
        }

    except Exception as exc:
        rprint(f"[yellow]Warning: sun info lookup failed: {exc}[/yellow]")
        return unavailable


def get_monthly_sun_table(lat: float, lon: float) -> list[dict]:
    """
    Compute golden hour times and sun azimuths for the 15th of each month.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.

    Returns:
        List of 12 dicts (Jan–Dec), each with keys:
            month_name, sunrise_utc, sunset_utc,
            golden_hour_morning_azimuth, golden_hour_evening_azimuth
    """
    year = datetime.date.today().year
    table = []

    for month_idx in range(1, 13):
        month_name = MONTH_NAMES[month_idx - 1]
        d = datetime.date(year, month_idx, 15)

        try:
            observer = _make_observer(lat, lon)
            s = sun(observer, date=d, tzinfo=datetime.timezone.utc)

            sunrise_utc = s["sunrise"]
            sunset_utc = s["sunset"]

            morning_mid = sunrise_utc + datetime.timedelta(minutes=45)
            evening_mid = sunset_utc - datetime.timedelta(minutes=45)

            morning_az = azimuth(observer, morning_mid)
            evening_az = azimuth(observer, evening_mid)

            table.append({
                "month_name": month_name,
                "sunrise_utc": sunrise_utc,
                "sunset_utc": sunset_utc,
                "golden_hour_morning_azimuth": round(morning_az, 1),
                "golden_hour_evening_azimuth": round(evening_az, 1),
            })

        except Exception as exc:
            rprint(f"[yellow]Warning: sun table for {month_name} failed: {exc}[/yellow]")
            table.append({
                "month_name": month_name,
                "sunrise_utc": None,
                "sunset_utc": None,
                "golden_hour_morning_azimuth": None,
                "golden_hour_evening_azimuth": None,
            })

    return table
