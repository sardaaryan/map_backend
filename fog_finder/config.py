DEFAULT_REGION = {
    "name": "California Central Coast & Bay Area",
    "lat_min": 35.0,
    "lat_max": 38.3,
    "lon_min": -123.2,
    "lon_max": -120.3,
}

# Your favourite shooting locations.
# elevation is metres ASL — look it up on Google Maps (right-click → elevation)
# or leave it as None to auto-detect from the nearest grid point.
FAVORITE_SPOTS = [
    {"name": "Mount Tam East Peak",  "lat": 37.9289, "lon": -122.5779, "elevation": 784},
    {"name": "Cerro Alto",           "lat": 35.4145, "lon": -120.7338, "elevation": 799},
]

GRID_ROWS = 10
GRID_COLS = 10
FORECAST_DAYS = 3
OUTPUT_FILE = "fog_map.html"
MAX_WORKERS = 5
