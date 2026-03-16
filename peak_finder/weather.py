"""
Open-Meteo current weather lookup for peak_finder.
No API key required.
"""

import requests
from rich import print as rprint

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather interpretation codes → human-readable description
WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _wmo_description(code: int) -> str:
    """Map a WMO weather code to a human-readable string."""
    if code in WMO_DESCRIPTIONS:
        return WMO_DESCRIPTIONS[code]
    # Range-based fallback
    if 1 <= code <= 3:
        return "Partly cloudy"
    if 45 <= code <= 48:
        return "Fog"
    if 51 <= code <= 67:
        return "Rain / drizzle"
    if 71 <= code <= 77:
        return "Snow"
    if 80 <= code <= 82:
        return "Rain showers"
    if 85 <= code <= 86:
        return "Snow showers"
    if 95 <= code <= 99:
        return "Thunderstorm"
    return "Unknown"


def get_weather(lat: float, lon: float) -> dict:
    """
    Fetch current weather conditions from Open-Meteo (no API key needed).

    Args:
        lat: Latitude of the location.
        lon: Longitude of the location.

    Returns:
        Dict with keys:
            cloud_cover_pct   – integer 0-100
            visibility_m      – visibility in metres (float)
            weather_code      – WMO weather code (int)
            temperature_c     – temperature in °C (float)
            clear_chance_pct  – estimated clear-sky percentage (int)
            description       – human-readable weather string
        On failure returns an "unavailable" dict.
    """
    unavailable = {
        "cloud_cover_pct": None,
        "visibility_m": None,
        "weather_code": None,
        "temperature_c": None,
        "clear_chance_pct": None,
        "description": "unavailable",
    }

    try:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "cloud_cover,visibility,weather_code,temperature_2m",
            "timezone": "auto",
        }
        response = requests.get(OPEN_METEO_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        rprint(f"[yellow]Warning: weather lookup failed: {exc}[/yellow]")
        return unavailable

    try:
        current = data.get("current", {})
        cloud_cover = int(current.get("cloud_cover", 0) or 0)
        visibility = float(current.get("visibility", 0) or 0)
        weather_code = int(current.get("weather_code", 0) or 0)
        temperature = float(current.get("temperature_2m", 0) or 0)
        clear_chance = max(0, 100 - cloud_cover)

        return {
            "cloud_cover_pct": cloud_cover,
            "visibility_m": visibility,
            "weather_code": weather_code,
            "temperature_c": temperature,
            "clear_chance_pct": clear_chance,
            "description": _wmo_description(weather_code),
        }
    except Exception as exc:
        rprint(f"[yellow]Warning: failed to parse weather data: {exc}[/yellow]")
        return unavailable
