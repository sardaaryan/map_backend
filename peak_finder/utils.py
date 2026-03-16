"""
Utility functions for peak_finder: haversine distance, bearing, compass direction.
"""

import math


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

    Args:
        lat1, lon1: Latitude/longitude of point 1 in decimal degrees.
        lat2, lon2: Latitude/longitude of point 2 in decimal degrees.

    Returns:
        Distance in kilometers.
    """
    R = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the initial compass bearing from point 1 to point 2.

    Args:
        lat1, lon1: Starting point in decimal degrees.
        lat2, lon2: Destination point in decimal degrees.

    Returns:
        Bearing in degrees (0 = North, 90 = East, 180 = South, 270 = West).
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)

    theta = math.atan2(x, y)
    return (math.degrees(theta) + 360) % 360


def compass_dir(degrees: float) -> str:
    """
    Convert a bearing in degrees to a compass direction string.

    Args:
        degrees: Bearing in degrees (0-360).

    Returns:
        Cardinal/intercardinal direction string: N, NNE, NE, ENE, E, ESE, SE, SSE,
        S, SSW, SW, WSW, W, WNW, NW, NNW.
    """
    directions = [
        "N", "NNE", "NE", "ENE",
        "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW",
        "W", "WNW", "NW", "NNW",
    ]
    # Each sector is 22.5 degrees wide; offset by half sector to centre on N
    index = int((degrees + 11.25) / 22.5) % 16
    return directions[index]
