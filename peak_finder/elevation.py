"""
SRTM elevation tile download and DEM assembly for peak_finder.
Tiles sourced from https://elevation-tiles-prod.s3.amazonaws.com/skadi/
"""

import gzip
import math
from pathlib import Path

import numpy as np
import requests
from scipy.ndimage import generic_filter
from rich import print as rprint

CACHE_DIR = Path.home() / ".peak_finder_cache"
TILE_SIZE = 3601  # SRTM1: 3601×3601 samples per 1°×1° tile
VOID_VALUE = -32768
BASE_URL = "https://elevation-tiles-prod.s3.amazonaws.com/skadi"


def _tile_name(lat_floor: int, lon_floor: int) -> tuple[str, str]:
    """
    Return (lat_dir, tile_name) for a given floor lat/lon.

    Examples:
        lat=45, lon=-122 -> ("N45", "N45W122")
        lat=-34, lon=18  -> ("S34", "S34E018")
    """
    lat_prefix = "N" if lat_floor >= 0 else "S"
    lon_prefix = "E" if lon_floor >= 0 else "W"

    abs_lat = abs(lat_floor)
    abs_lon = abs(lon_floor)

    lat_dir = f"{lat_prefix}{abs_lat:02d}"
    tile_name = f"{lat_prefix}{abs_lat:02d}{lon_prefix}{abs_lon:03d}"
    return lat_dir, tile_name


def _download_tile(lat_floor: int, lon_floor: int) -> Path:
    """
    Download and gunzip an SRTM HGT tile, caching in ~/.peak_finder_cache/.

    Args:
        lat_floor: Floor of the latitude (integer).
        lon_floor: Floor of the longitude (integer).

    Returns:
        Path to the local .hgt file.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    lat_dir, tile_name = _tile_name(lat_floor, lon_floor)
    hgt_path = CACHE_DIR / f"{tile_name}.hgt"

    if hgt_path.exists():
        rprint(f"[green]Using cached tile:[/green] {tile_name}")
        return hgt_path

    url = f"{BASE_URL}/{lat_dir}/{tile_name}.hgt.gz"
    rprint(f"[cyan]Downloading tile:[/cyan] {tile_name} from {url}")

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Failed to download SRTM tile {tile_name}: {exc}\n"
            "This area may not have SRTM coverage (ocean or high-latitude region)."
        ) from exc

    gz_data = response.content
    try:
        raw_data = gzip.decompress(gz_data)
    except Exception as exc:
        raise RuntimeError(f"Failed to decompress tile {tile_name}: {exc}") from exc

    hgt_path.write_bytes(raw_data)
    rprint(f"[green]Saved:[/green] {hgt_path}")
    return hgt_path


def _parse_hgt(path: Path) -> np.ndarray:
    """
    Parse an HGT file into a float32 numpy array with voids replaced by NaN.

    HGT format: 3601×3601 big-endian signed 16-bit integers.
    First row = northernmost latitude, first column = westernmost longitude.

    Args:
        path: Path to the .hgt file.

    Returns:
        Array of shape (3601, 3601) with dtype float32.
    """
    raw = np.frombuffer(path.read_bytes(), dtype=">i2")
    if raw.size != TILE_SIZE * TILE_SIZE:
        raise ValueError(
            f"Unexpected HGT file size {raw.size} (expected {TILE_SIZE * TILE_SIZE}) for {path}"
        )
    arr = raw.reshape((TILE_SIZE, TILE_SIZE)).astype(np.float32)
    arr[arr == VOID_VALUE] = np.nan
    return arr


def get_dem(
    center_lat: float,
    center_lon: float,
    radius_km: float,
    subsample: int = 3,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Download SRTM tiles and assemble a DEM covering center ± radius * 1.1.

    Args:
        center_lat:  Center latitude in decimal degrees.
        center_lon:  Center longitude in decimal degrees.
        radius_km:   Search radius in kilometres.
        subsample:   Take every Nth point to reduce resolution (default 3 → ~90 m).

    Returns:
        (dem, lats, lons, pixel_size_m) where:
            dem          – 2-D float32 array (rows=lat, cols=lon), NaN-filled voids
            lats         – 1-D array of latitude values, descending (north first)
            lons         – 1-D array of longitude values, ascending (west first)
            pixel_size_m – approximate metres per pixel after subsampling
    """
    # Determine the geographic bounding box to cover
    padding = 1.1
    # 1 degree latitude ≈ 111 km
    deg_radius = (radius_km * padding) / 111.0

    lat_min = center_lat - deg_radius
    lat_max = center_lat + deg_radius
    lon_min = center_lon - deg_radius / math.cos(math.radians(center_lat))
    lon_max = center_lon + deg_radius / math.cos(math.radians(center_lat))

    # Determine which integer-degree tiles are needed
    lat_floors = list(range(math.floor(lat_min), math.floor(lat_max) + 1))
    lon_floors = list(range(math.floor(lon_min), math.floor(lon_max) + 1))

    if not lat_floors or not lon_floors:
        raise ValueError("Could not determine tile range — check your coordinates.")

    # Download all tiles
    tiles: dict[tuple[int, int], np.ndarray] = {}
    for lf in lat_floors:
        for lof in lon_floors:
            path = _download_tile(lf, lof)
            tiles[(lf, lof)] = _parse_hgt(path)

    # Build the full coordinate arrays for the assembled region.
    # SRTM tiles share edge pixels — adjacent tiles' edges are identical.
    # We assemble by stacking tiles and deduplicating shared edges.

    # Full lat/lon arrays for the assembled multi-tile grid (before subsample)
    # Latitude: tile top_lat → top_lat-1 (descending), TILE_SIZE points per tile
    # Because adjacent tiles share an edge pixel we remove the duplicate.

    all_lat_floors_sorted = sorted(lat_floors, reverse=True)  # north to south
    all_lon_floors_sorted = sorted(lon_floors)                 # west to east

    n_tiles_lat = len(all_lat_floors_sorted)
    n_tiles_lon = len(all_lon_floors_sorted)

    # Total grid size (sharing edges between tiles)
    total_rows = (TILE_SIZE - 1) * n_tiles_lat + 1
    total_cols = (TILE_SIZE - 1) * n_tiles_lon + 1

    full_dem = np.full((total_rows, total_cols), np.nan, dtype=np.float32)

    # Build full latitude/longitude arrays
    # Top-left is (max_lat_floor + 1, min_lon_floor)
    top_lat = all_lat_floors_sorted[0] + 1.0      # northernmost latitude
    left_lon = all_lon_floors_sorted[0] + 0.0     # westernmost longitude

    full_lats = np.linspace(top_lat, top_lat - n_tiles_lat, total_rows, dtype=np.float64)
    full_lons = np.linspace(left_lon, left_lon + n_tiles_lon, total_cols, dtype=np.float64)

    # Fill tiles into the assembled grid using vectorized indexing
    for tile_row_idx, lf in enumerate(all_lat_floors_sorted):
        for tile_col_idx, lof in enumerate(all_lon_floors_sorted):
            tile_arr = tiles[(lf, lof)]

            # Output slice for this tile (row/col start in full_dem)
            out_row_start = tile_row_idx * (TILE_SIZE - 1)
            out_row_end = out_row_start + TILE_SIZE
            out_col_start = tile_col_idx * (TILE_SIZE - 1)
            out_col_end = out_col_start + TILE_SIZE

            tile_top_lat = float(lf + 1)
            tile_left_lon = float(lof)

            # Compute which tile rows/cols correspond to the output grid region
            region_lats = full_lats[out_row_start:out_row_end]
            region_lons = full_lons[out_col_start:out_col_end]

            n = TILE_SIZE
            local_r = np.round((tile_top_lat - region_lats) * (n - 1)).astype(np.int32)
            local_c = np.round((region_lons - tile_left_lon) * (n - 1)).astype(np.int32)
            local_r = np.clip(local_r, 0, n - 1)
            local_c = np.clip(local_c, 0, n - 1)

            full_dem[out_row_start:out_row_end, out_col_start:out_col_end] = (
                tile_arr[local_r[:, None], local_c[None, :]]
            )

    # Crop to the actual requested bounding box (with padding)
    row_start = int(np.searchsorted(-full_lats, -lat_max))
    row_end = int(np.searchsorted(-full_lats, -lat_min, side="right"))
    col_start = int(np.searchsorted(full_lons, lon_min))
    col_end = int(np.searchsorted(full_lons, lon_max, side="right"))

    row_start = max(row_start, 0)
    row_end = min(row_end, total_rows)
    col_start = max(col_start, 0)
    col_end = min(col_end, total_cols)

    cropped_dem = full_dem[row_start:row_end, col_start:col_end]
    cropped_lats = full_lats[row_start:row_end]
    cropped_lons = full_lons[col_start:col_end]

    # Subsample
    dem = cropped_dem[::subsample, ::subsample].copy()
    lats = cropped_lats[::subsample].copy()
    lons = cropped_lons[::subsample].copy()

    # Fill remaining NaN voids using a 3×3 mean filter
    nan_mask = np.isnan(dem)
    if nan_mask.any():
        def _nanmean(values: np.ndarray) -> float:
            valid = values[values != VOID_VALUE]
            finite = valid[np.isfinite(valid)]
            return float(np.mean(finite)) if finite.size > 0 else np.nan

        # Use generic_filter with a function that handles NaN
        filled = generic_filter(
            dem,
            function=lambda v: float(np.nanmean(v)) if np.any(np.isfinite(v)) else np.nan,
            size=3,
            mode="nearest",
        )
        dem = np.where(nan_mask, filled, dem)

    # Compute approximate pixel size in metres
    # Use the spacing between two consecutive latitude steps
    if lats.size >= 2:
        dlat_deg = abs(float(lats[0]) - float(lats[1]))
    else:
        dlat_deg = subsample / (TILE_SIZE - 1)  # fallback: 1 tile step
    pixel_size_m = dlat_deg * 111_000.0  # metres per degree latitude ≈ 111 km

    rprint(
        f"[green]DEM assembled:[/green] {dem.shape[0]}×{dem.shape[1]} pixels, "
        f"pixel size ≈ {pixel_size_m:.1f} m"
    )

    return dem, lats, lons, pixel_size_m
