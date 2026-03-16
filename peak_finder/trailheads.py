"""
OSM trailhead lookup via the Overpass API for peak_finder.
"""

import requests
from rich import print as rprint

try:
    from .utils import haversine
except ImportError:
    from utils import haversine  # type: ignore[no-redef]


OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def find_nearest_trailhead(
    lat: float,
    lon: float,
    search_radius_km: float = 25.0,
) -> dict | None:
    """
    Find the nearest OSM trailhead node within search_radius_km of (lat, lon).

    Queries the Overpass API for nodes tagged highway=trailhead or
    tourism=trailhead. Returns the closest result by haversine distance, or
    None if nothing is found or the request fails.

    Args:
        lat:              Observer latitude.
        lon:              Observer longitude.
        search_radius_km: Search radius in km (converted to metres for Overpass).

    Returns:
        Dict {lat, lon, name, distance_km} or None.
    """
    radius_m = int(search_radius_km * 1000)
    query = (
        f"[out:json][timeout:25];\n"
        f"(\n"
        f'  node["highway"="trailhead"](around:{radius_m},{lat},{lon});\n'
        f'  node["tourism"="trailhead"](around:{radius_m},{lat},{lon});\n'
        f");\n"
        f"out body;\n"
    )

    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        rprint(f"[yellow]Warning: trailhead lookup failed: {exc}[/yellow]")
        return None

    elements = data.get("elements", [])
    if not elements:
        return None

    # Find the nearest trailhead by haversine distance
    best = None
    best_dist = float("inf")
    for elem in elements:
        th_lat = elem.get("lat")
        th_lon = elem.get("lon")
        if th_lat is None or th_lon is None:
            continue
        dist = haversine(lat, lon, th_lat, th_lon)
        if dist < best_dist:
            best_dist = dist
            tags = elem.get("tags", {})
            name = (
                tags.get("name")
                or tags.get("official_name")
                or tags.get("ref")
                or "Unnamed trailhead"
            )
            best = {
                "lat": th_lat,
                "lon": th_lon,
                "name": name,
                "distance_km": round(dist, 2),
            }

    return best


def lookup_peak_name(lat: float, lon: float, search_radius_m: int = 800) -> str | None:
    """
    Return the OSM name of a named peak near (lat, lon), or None if not found.

    Queries for natural=peak nodes within search_radius_m metres.
    Returns the name of the closest match.
    """
    query = (
        f"[out:json][timeout:10];\n"
        f'node["natural"="peak"](around:{search_radius_m},{lat},{lon});\n'
        f"out body;\n"
    )
    try:
        response = requests.post(OVERPASS_URL, data={"data": query}, timeout=15)
        response.raise_for_status()
        elements = response.json().get("elements", [])
    except Exception:
        return None

    best_name = None
    best_dist = float("inf")
    for elem in elements:
        name = elem.get("tags", {}).get("name")
        if not name:
            continue
        dist = haversine(lat, lon, elem["lat"], elem["lon"])
        if dist < best_dist:
            best_dist = dist
            best_name = name

    return best_name
