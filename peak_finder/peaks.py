"""
Peak detection and filtering for peak_finder.
"""

import numpy as np
from scipy.ndimage import maximum_filter

try:
    from .utils import haversine
except ImportError:
    from utils import haversine  # type: ignore[no-redef]


def find_peaks(
    dem: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    center_lat: float,
    center_lon: float,
    radius_km: float,
    min_prominence_m: float = 100.0,
    window_size: int = 15,
    max_candidates: int = 30,
) -> list[dict]:
    """
    Find candidate mountain peaks within radius_km of (center_lat, center_lon).

    Uses a sliding-window maximum filter to detect local maxima in the DEM.

    Args:
        dem:              2-D elevation array (float32), NaN = no data.
        lats:             1-D latitude array (descending, north first).
        lons:             1-D longitude array (ascending, west first).
        center_lat:       Center of search area (latitude).
        center_lon:       Center of search area (longitude).
        radius_km:        Maximum distance from center to consider a peak.
        min_prominence_m: Minimum elevation above surroundings to qualify.
                          Currently used as a sanity floor: peaks below the
                          local window minimum by less than this are discarded.
        window_size:      Size of the local-maximum filter window (pixels).
        max_candidates:   Maximum number of peaks to return (sorted by elevation).

    Returns:
        List of dicts: {lat, lon, elevation_m, row, col}
    """
    # Local maxima: pixels equal to the maximum within their window
    local_max = maximum_filter(dem, size=window_size) == dem

    # Exclude NaN and flat-zero areas
    local_max &= ~np.isnan(dem)
    local_max &= dem > 0

    rows, cols = np.where(local_max)

    peaks = []
    for r, c in zip(rows, cols):
        elev = float(dem[r, c])
        lat = float(lats[r])
        lon = float(lons[c])

        dist = haversine(center_lat, center_lon, lat, lon)
        if dist > radius_km:
            continue

        # Simple prominence check: elevation must exceed local window mean by min_prominence_m
        r0 = max(0, r - window_size // 2)
        r1 = min(dem.shape[0], r + window_size // 2 + 1)
        c0 = max(0, c - window_size // 2)
        c1 = min(dem.shape[1], c + window_size // 2 + 1)
        window = dem[r0:r1, c0:c1]
        window_min = float(np.nanmin(window))

        if elev - window_min < min_prominence_m:
            continue

        peaks.append({
            "lat": lat,
            "lon": lon,
            "elevation_m": elev,
            "row": int(r),
            "col": int(c),
        })

    # Sort by elevation, keep top candidates
    peaks.sort(key=lambda p: p["elevation_m"], reverse=True)
    return peaks[:max_candidates]


def filter_shadowed_peaks(
    peaks: list[dict],
    shadow_radius_km: float = 8.0,
    shadow_height_advantage_m: float = 200.0,
) -> list[dict]:
    """
    Remove peaks that are likely 'shadowed' by a nearby taller peak.

    A peak P is considered shadowed if there exists any other peak Q within
    shadow_radius_km that is at least shadow_height_advantage_m taller than P.

    Args:
        peaks:                   List of peak dicts as returned by find_peaks().
        shadow_radius_km:        Radius within which to look for shadowing peaks.
        shadow_height_advantage_m: Height advantage that constitutes shadowing.

    Returns:
        Filtered list of unshadowed peaks.
    """
    unshadowed = []
    for i, peak in enumerate(peaks):
        shadowed = False
        for j, other in enumerate(peaks):
            if i == j:
                continue
            dist = haversine(peak["lat"], peak["lon"], other["lat"], other["lon"])
            if dist <= shadow_radius_km:
                if other["elevation_m"] > peak["elevation_m"] + shadow_height_advantage_m:
                    shadowed = True
                    break
        if not shadowed:
            unshadowed.append(peak)
    return unshadowed
