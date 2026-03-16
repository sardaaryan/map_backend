"""
Vectorized ray-casting viewshed analysis for peak_finder.
"""

import math

import numpy as np


def compute_viewshed_score(
    dem: np.ndarray,
    center_row: int,
    center_col: int,
    pixel_size_m: float,
    max_dist_m: float,
    n_angles: int = 360,
    observer_height: float = 2.0,
) -> float:
    """
    Compute the viewshed score (visible area in km²) for an observer point.

    Casts n_angles rays outward from the observer, tracking the maximum
    vertical angle seen so far along each ray. A terrain cell is visible
    if its apparent vertical angle (corrected for Earth curvature) equals
    or exceeds the maximum seen so far on that ray.

    Args:
        dem:             2-D elevation array (float, metres, NaN = no data).
        center_row:      Row index of the observer in dem.
        center_col:      Column index of the observer in dem.
        pixel_size_m:    Metres per pixel (used to convert pixel steps to metres).
        max_dist_m:      Maximum ray length in metres.
        n_angles:        Number of rays to cast (evenly spaced 0–360°).
        observer_height: Observer height above terrain in metres.

    Returns:
        Visible area in km² (unique cells × pixel_size_m² / 1e6).
    """
    rows, cols = dem.shape
    max_dist_px = int(math.ceil(max_dist_m / pixel_size_m))

    # Observer elevation
    obs_elev = dem[center_row, center_col]
    if np.isnan(obs_elev):
        return 0.0
    observer_elev = float(obs_elev) + observer_height

    # Pre-compute angle vectors for all rays
    angles_deg = np.linspace(0.0, 360.0, n_angles, endpoint=False)
    angles_rad = np.radians(angles_deg)
    # Convention: 0° = North (row decreases), 90° = East (col increases)
    cos_a = np.cos(angles_rad)  # used for row direction (north component)
    sin_a = np.sin(angles_rad)  # used for col direction (east component)

    # Track the maximum vertical angle reached along each ray (initialised to -inf)
    max_angle_per_ray = np.full(n_angles, -np.pi / 2.0, dtype=np.float64)

    # Boolean grid: has this cell been counted as visible?
    counted = np.zeros((rows, cols), dtype=bool)

    EARTH_R = 6_371_000.0  # metres

    for d in range(1, max_dist_px + 1):
        dist_m = d * pixel_size_m

        # Fractional row/col for each ray
        r_float = center_row - cos_a * d   # row decreases going north
        c_float = center_col + sin_a * d

        # Integer indices (nearest-neighbour)
        r_idx = r_float.astype(np.int32)
        c_idx = c_float.astype(np.int32)

        # Validity mask: within grid bounds
        valid = (
            (r_idx >= 0) & (r_idx < rows) &
            (c_idx >= 0) & (c_idx < cols)
        )

        if not valid.any():
            break  # All rays have left the grid

        # Gather terrain elevation for valid rays; NaN for invalid
        terrain_elev = np.full(n_angles, np.nan, dtype=np.float64)
        terrain_elev[valid] = dem[r_idx[valid], c_idx[valid]]

        # Earth curvature correction
        curvature = (dist_m * dist_m) / (2.0 * EARTH_R)
        apparent_elev = terrain_elev - curvature

        # Vertical angle from observer to this point
        vert_angle = np.arctan2(apparent_elev - observer_elev, dist_m)

        # A cell is visible if it is valid, not NaN, and angle >= max so far
        not_nan = ~np.isnan(terrain_elev)
        is_visible = valid & not_nan & (vert_angle >= max_angle_per_ray)

        # Update max angle where this point is visible OR simply higher than previous
        # (even occluded points raise the horizon for subsequent points)
        update_horizon = valid & not_nan & (vert_angle > max_angle_per_ray)
        max_angle_per_ray = np.where(update_horizon, vert_angle, max_angle_per_ray)

        # Mark visible cells (avoid double-counting)
        vis_r = r_idx[is_visible]
        vis_c = c_idx[is_visible]
        counted[vis_r, vis_c] = True

    # Include the observer cell itself
    counted[center_row, center_col] = True

    visible_cells = int(counted.sum())
    visible_area_km2 = visible_cells * (pixel_size_m ** 2) / 1e6
    return visible_area_km2
