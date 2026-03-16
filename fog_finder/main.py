"""
fog_finder/main.py

Valley fog & cloud inversion prediction map for photography.

Usage examples:
  python main.py                            # Willamette Valley (default)
  python main.py --name "Napa Valley" --lat-min 38.1 --lat-max 38.7 --lon-min -122.6 --lon-max -122.2
  python main.py --grid 12 --days 5
"""

import argparse
import os
import webbrowser

import numpy as np

from config import DEFAULT_REGION, GRID_ROWS, GRID_COLS, FORECAST_DAYS, OUTPUT_FILE, MAX_WORKERS, FAVORITE_SPOTS
from weather import fetch_grid
from fog_model import compute_fog_grid
from map_viz import create_map


def make_grid(lat_min, lat_max, lon_min, lon_max, rows, cols):
    lats = np.linspace(lat_min, lat_max, rows)
    lons = np.linspace(lon_min, lon_max, cols)
    return [(float(lat), float(lon)) for lat in lats for lon in lons]


def print_summary(fog_data):
    grid  = fog_data["grid"]
    times = fog_data["times"]

    all_scores = [s for p in grid for s in p["fog_scores"]]
    print(f"\n  Peak fog probability : {max(all_scores):.0%}")
    print(f"  Mean fog probability : {np.mean(all_scores):.0%}")

    # Find the single best hour across all points
    best_score = 0
    best_point = None
    best_time  = ""
    for p in grid:
        idx = int(np.argmax(p["fog_scores"]))
        if p["fog_scores"][idx] > best_score:
            best_score = p["fog_scores"][idx]
            best_point = p
            best_time  = times[idx]

    if best_point:
        h = int(best_time[11:13])
        suffix = "AM" if h < 12 else "PM"
        h12    = h % 12 or 12
        print(f"  Best window          : {best_time[:10]}  {h12}:00 {suffix}  "
              f"({best_score:.0%} at {best_point['lat']:.2f}°N, {best_point['lon']:.2f}°)")


def main():
    parser = argparse.ArgumentParser(
        description="Valley fog prediction map for photography"
    )
    r = DEFAULT_REGION
    parser.add_argument("--lat-min", type=float, default=r["lat_min"])
    parser.add_argument("--lat-max", type=float, default=r["lat_max"])
    parser.add_argument("--lon-min", type=float, default=r["lon_min"])
    parser.add_argument("--lon-max", type=float, default=r["lon_max"])
    parser.add_argument("--name",    default=r["name"])
    parser.add_argument("--days",    type=int, default=FORECAST_DAYS)
    parser.add_argument("--grid",    type=int, default=GRID_ROWS,
                        help="Grid size N (creates N×N points, default 10)")
    parser.add_argument("--output",  default=OUTPUT_FILE)
    parser.add_argument("--no-open", action="store_true",
                        help="Don't open the map in a browser automatically")
    args = parser.parse_args()

    n_points = args.grid ** 2
    print(f"\n  Valley Fog Prediction Map")
    print(f"  Region   : {args.name}")
    print(f"  Bounds   : {args.lat_min:.2f}–{args.lat_max:.2f} N, "
          f"{args.lon_min:.2f}–{args.lon_max:.2f}")
    print(f"  Grid     : {args.grid}x{args.grid} = {n_points} points")
    print(f"  Forecast : {args.days} days\n")

    # 1. Build grid
    grid_points = make_grid(
        args.lat_min, args.lat_max,
        args.lon_min, args.lon_max,
        args.grid, args.grid,
    )

    # 2. Fetch weather
    weather_data = fetch_grid(grid_points, forecast_days=args.days, max_workers=MAX_WORKERS)
    if not weather_data:
        print("Error: no weather data fetched. Check your internet connection.")
        return

    # 3. Score fog
    print("  Computing fog probabilities...")
    fog_data = compute_fog_grid(weather_data)

    # 4. Print summary
    print_summary(fog_data)

    # 5. Generate map
    print("\n  Generating interactive map...")
    output_path = os.path.abspath(args.output)
    create_map(fog_data, favorite_spots=FAVORITE_SPOTS, output_file=output_path)

    if not args.no_open:
        print("  Opening in browser...")
        webbrowser.open(f"file:///{output_path}")

    print("\n  Done!")


if __name__ == "__main__":
    main()
