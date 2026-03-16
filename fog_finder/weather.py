import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def fetch_point(lat, lon, forecast_days=3):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relativehumidity_2m,dewpoint_2m,windspeed_10m,cloudcover,precipitation,boundary_layer_height",
        "daily": "sunrise,sunset",
        "forecast_days": forecast_days,
        "timezone": "auto",
    }
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return {
        "lat": lat,
        "lon": lon,
        "elevation": data.get("elevation", 0),
        "hourly": data["hourly"],
        "daily": data["daily"],
        "timezone": data.get("timezone", "UTC"),
    }


def fetch_grid(grid_points, forecast_days=3, max_workers=10):
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_point, lat, lon, forecast_days): (lat, lon)
            for lat, lon in grid_points
        }
        total = len(futures)
        done = 0
        for future in as_completed(futures):
            done += 1
            print(f"\r  Fetching weather data... {done}/{total}", end="", flush=True)
            try:
                results.append(future.result())
            except Exception as e:
                lat, lon = futures[future]
                print(f"\n  Warning: failed to fetch ({lat:.2f}, {lon:.2f}): {e}")
    print()
    return results
