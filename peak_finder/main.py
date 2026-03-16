"""
Peak Finder — CLI entry point.
Finds and ranks mountain viewpoints by visible area (viewshed analysis).

Usage:
    python main.py --lat 45.3721 --lon -121.6959 --radius 30
"""

import argparse
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed

# Force UTF-8 output on Windows so Rich unicode characters render correctly
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests

from rich import print as rprint
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from elevation import get_dem
from peaks import find_peaks, filter_shadowed_peaks
from viewshed import compute_viewshed_score
from trailheads import find_nearest_trailhead, lookup_peak_name
from weather import get_weather
from sun_analysis import get_sun_info
from map_output import generate_map
from utils import haversine

console = Console()


def geocode(place: str) -> tuple[float, float]:
    """Resolve a place name to (lat, lon) using OSM Nominatim."""
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": place, "format": "json", "limit": 1},
        headers={"User-Agent": "peak-finder/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json()
    if not results:
        raise ValueError(f"Could not find location: '{place}'")
    r = results[0]
    return float(r["lat"]), float(r["lon"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="peak_finder",
        description="Find mountain viewpoints ranked by viewshed score.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    loc_group = parser.add_mutually_exclusive_group(required=True)
    loc_group.add_argument("--location", type=str, metavar="PLACE",
                           help="Place name to search around (e.g. 'Mount Hood Oregon')")
    loc_group.add_argument("--lat", type=float, help="Center latitude (use with --lon)")
    parser.add_argument("--lon", type=float, help="Center longitude (required with --lat)")
    parser.add_argument("--radius", type=float, default=30.0, help="Search radius in km")
    parser.add_argument(
        "--max-dist", type=float, default=80.0,
        help="Max viewshed ray distance in km",
    )
    parser.add_argument("--top", type=int, default=5, help="Number of top peaks to show")
    parser.add_argument(
        "--subsample", type=int, default=3,
        help="DEM resolution: take every Nth point (3 = ~90m resolution)",
    )
    parser.add_argument("--no-map", action="store_true", help="Skip HTML map generation")
    parser.add_argument("--no-weather", action="store_true", help="Skip weather lookup")
    parser.add_argument("--no-trailheads", action="store_true", help="Skip trailhead lookup")
    parser.add_argument(
        "--output", default="peak_finder_results.html",
        help="Output HTML map path",
    )
    return parser.parse_args()


def _fmt_elev(m: float) -> str:
    ft = m * 3.28084
    return f"{ft:,.0f} ft ({m:,.0f} m)"


def _fmt_score(km2: float) -> str:
    mi2 = km2 * 0.386102
    return f"{mi2:.0f} mi² ({km2:.0f} km²)"


def _fmt_dist(km: float | None) -> str:
    if km is None:
        return "—"
    mi = km * 0.621371
    return f"{mi:.1f} mi ({km:.1f} km)"


def _fmt_temp(c: float | None) -> str:
    if c is None:
        return "—"
    f = c * 9 / 5 + 32
    return f"{f:.0f} °F ({c:.0f} °C)"


def _compute_elevation_gain(peak: dict, trailhead: dict | None, center_lat: float, center_lon: float, dem, lats, lons) -> int | None:
    """
    Estimate elevation gain to reach the peak.
    If a trailhead is available, uses trailhead elevation from the DEM.
    Falls back to center point elevation.
    """
    import numpy as np

    peak_elev = peak["elevation_m"]

    # Determine reference point
    if trailhead:
        ref_lat = trailhead["lat"]
        ref_lon = trailhead["lon"]
    else:
        ref_lat = center_lat
        ref_lon = center_lon

    # Find nearest DEM cell for the reference point
    r_idx = int(np.argmin(np.abs(lats - ref_lat)))
    c_idx = int(np.argmin(np.abs(lons - ref_lon)))
    ref_elev = float(dem[r_idx, c_idx])

    if np.isnan(ref_elev):
        return None

    gain = peak_elev - ref_elev
    return max(0, int(gain))


def _enrich_peak(
    peak: dict,
    center_lat: float,
    center_lon: float,
    dem,
    lats,
    lons,
    no_weather: bool,
    no_trailheads: bool,
) -> dict:
    """Fetch trailhead, weather, sun info and elevation gain for one peak."""
    enriched = dict(peak)

    # Peak name from OSM
    enriched["name"] = lookup_peak_name(peak["lat"], peak["lon"]) or "Unnamed Peak"

    # Trailhead
    trailhead = None
    if not no_trailheads:
        trailhead = find_nearest_trailhead(peak["lat"], peak["lon"])
    enriched["trailhead"] = trailhead

    # Weather
    weather = None
    if not no_weather:
        weather = get_weather(peak["lat"], peak["lon"])
    enriched["weather"] = weather

    # Sun info
    sun_info = get_sun_info(peak["lat"], peak["lon"])
    enriched["sun_info"] = sun_info

    # Elevation gain
    elev_gain = _compute_elevation_gain(
        peak, trailhead, center_lat, center_lon, dem, lats, lons
    )
    enriched["elevation_gain_m"] = elev_gain

    return enriched


def _print_detailed_peak(peak: dict) -> None:
    """Print detailed information about the top-ranked peak."""
    sun = peak.get("sun_info") or {}
    weather = peak.get("weather") or {}
    trailhead = peak.get("trailhead")

    rprint("\n[bold yellow]━━━ #1 Peak — Detailed Report ━━━[/bold yellow]")
    rprint(f"[bold]Location:[/bold] {peak['lat']:.4f}°, {peak['lon']:.4f}°")
    rprint(f"[bold]Elevation:[/bold] {peak['elevation_m']:,.0f} m")
    rprint(f"[bold]Viewshed Score:[/bold] {peak['score_km2']:.0f} km²")

    if trailhead:
        rprint(
            f"[bold]Nearest Trailhead:[/bold] {trailhead['name']} "
            f"({trailhead['distance_km']:.1f} km away)"
        )
    else:
        rprint("[bold]Nearest Trailhead:[/bold] Not found")

    gain = peak.get("elevation_gain_m")
    rprint(f"[bold]Elevation Gain:[/bold] {f'{gain:,} m' if gain is not None else '—'}")

    if weather and weather.get("description") != "unavailable":
        rprint(f"\n[bold cyan]Current Weather:[/bold cyan]")
        rprint(f"  Conditions:   {weather.get('description', '—')}")
        rprint(f"  Temperature:  {_fmt_temp(weather.get('temperature_c'))}")
        cc = weather.get('cloud_cover_pct')
        cl = weather.get('clear_chance_pct')
        if cc is not None:
            rprint(f"  Cloud cover:  {cc}%  |  Clear chance: {cl}%")
        vis = weather.get('visibility_m')
        if vis is not None:
            rprint(f"  Visibility:   {vis/1000:.1f} km")

    if sun.get("sunrise_utc"):
        rprint(f"\n[bold yellow]Sun Information (UTC):[/bold yellow]")
        rprint(f"  Sunrise:              {sun['sunrise_utc'].strftime('%H:%M')}")
        rprint(f"  Sunset:               {sun['sunset_utc'].strftime('%H:%M')}")
        gh_ms = sun.get("golden_hour_morning_start")
        gh_me = sun.get("golden_hour_morning_end")
        gh_es = sun.get("golden_hour_evening_start")
        gh_ee = sun.get("golden_hour_evening_end")
        gh_maz = sun.get("golden_hour_morning_azimuth")
        gh_eaz = sun.get("golden_hour_evening_azimuth")
        if gh_ms and gh_me:
            rprint(
                f"  Morning golden hour:  {gh_ms.strftime('%H:%M')} – {gh_me.strftime('%H:%M')}"
                + (f"  (sun at {gh_maz:.0f}°)" if gh_maz else "")
            )
        if gh_es and gh_ee:
            rprint(
                f"  Evening golden hour:  {gh_es.strftime('%H:%M')} – {gh_ee.strftime('%H:%M')}"
                + (f"  (sun at {gh_eaz:.0f}°)" if gh_eaz else "")
            )
        rprint(f"  Best photography months: {sun.get('best_months', '—')}")


def main() -> None:
    args = parse_args()

    # ── Resolve location ────────────────────────────────────────────────────
    if args.location:
        try:
            center_lat, center_lon = geocode(args.location)
            rprint(f"[dim]Resolved '{args.location}' -> {center_lat:.4f}, {center_lon:.4f}[/dim]")
        except Exception as exc:
            rprint(f"[bold red]Could not geocode location:[/bold red] {exc}")
            sys.exit(1)
    else:
        if args.lon is None:
            rprint("[bold red]--lon is required when using --lat[/bold red]")
            sys.exit(1)
        center_lat, center_lon = args.lat, args.lon

    # ── Header ─────────────────────────────────────────────────────────────
    console.rule("[bold green]Peak Finder — Viewshed Analysis[/bold green]")
    rprint(
        f"[bold]Centre:[/bold] {center_lat:.4f}°, {center_lon:.4f}°  |  "
        f"[bold]Radius:[/bold] {args.radius:.0f} km  |  "
        f"[bold]Max ray:[/bold] {args.max_dist:.0f} km  |  "
        f"[bold]Subsample:[/bold] {args.subsample}×"
    )
    console.rule()

    # ── Download DEM ────────────────────────────────────────────────────────
    rprint("\n[bold]Step 1/4:[/bold] Downloading elevation data (SRTM)…")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Fetching DEM tiles…", total=None)
        try:
            dem, lats, lons, pixel_size_m = get_dem(
                center_lat, center_lon, args.radius, subsample=args.subsample
            )
        except RuntimeError as exc:
            rprint(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)
        progress.update(task, completed=1, total=1)

    # ── Find peaks ──────────────────────────────────────────────────────────
    rprint("\n[bold]Step 2/4:[/bold] Detecting candidate peaks…")
    candidates = find_peaks(
        dem, lats, lons,
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=args.radius,
    )
    rprint(f"  Found [green]{len(candidates)}[/green] local maxima before filtering.")

    candidates = filter_shadowed_peaks(candidates)
    rprint(f"  [green]{len(candidates)}[/green] peaks remain after shadow filtering.")

    if not candidates:
        rprint("[bold red]No candidate peaks found.[/bold red] Try a larger radius or different area.")
        sys.exit(0)

    # ── Compute viewshed scores ─────────────────────────────────────────────
    rprint(f"\n[bold]Step 3/4:[/bold] Computing viewshed scores for {len(candidates)} peaks…")
    max_dist_m = args.max_dist * 1000.0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Analysing viewsheds", total=len(candidates))
        for peak in candidates:
            score = compute_viewshed_score(
                dem=dem,
                center_row=peak["row"],
                center_col=peak["col"],
                pixel_size_m=pixel_size_m,
                max_dist_m=max_dist_m,
            )
            peak["score_km2"] = score
            progress.advance(task)

    # Sort by score, assign ranks, take top N
    candidates.sort(key=lambda p: p["score_km2"], reverse=True)
    top_peaks = candidates[: args.top]
    for rank, peak in enumerate(top_peaks, start=1):
        peak["rank"] = rank

    # ── Enrich top peaks ────────────────────────────────────────────────────
    rprint(f"\n[bold]Step 4/4:[/bold] Fetching metadata for top {len(top_peaks)} peaks…")

    enriched_peaks: list[dict] = []

    def _enrich(peak: dict) -> dict:
        return _enrich_peak(
            peak,
            center_lat=center_lat,
            center_lon=center_lon,
            dem=dem,
            lats=lats,
            lons=lons,
            no_weather=args.no_weather,
            no_trailheads=args.no_trailheads,
        )

    with ThreadPoolExecutor(max_workers=min(len(top_peaks), 5)) as executor:
        futures = {executor.submit(_enrich, p): p for p in top_peaks}
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Fetching metadata", total=len(top_peaks))
            for future in as_completed(futures):
                enriched_peaks.append(future.result())
                progress.advance(task)

    # Re-sort by rank (concurrent results may be unordered)
    enriched_peaks.sort(key=lambda p: p["rank"])

    # ── Rich results table ──────────────────────────────────────────────────
    console.rule("[bold green]Results[/bold green]")

    table = Table(
        title=f"Top {len(enriched_peaks)} Mountain Viewpoints",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Rank", justify="center", style="bold yellow", no_wrap=True)
    table.add_column("Elevation", justify="right")
    table.add_column("Viewshed Score", justify="right", style="green")
    table.add_column("Trailhead Dist", justify="right")
    table.add_column("Elev Gain", justify="right")
    table.add_column("Weather", justify="left")
    table.add_column("Golden Hour (UTC)", justify="left")

    for peak in enriched_peaks:
        rank = peak["rank"]
        weather = peak.get("weather") or {}
        sun = peak.get("sun_info") or {}
        trailhead = peak.get("trailhead")

        th_dist = _fmt_dist(trailhead["distance_km"] if trailhead else None)
        gain = peak.get("elevation_gain_m")
        gain_str = f"{gain:,} m" if gain is not None else "—"

        weather_str = weather.get("description", "—")
        if weather.get("temperature_c") is not None:
            weather_str += f" {_fmt_temp(weather['temperature_c'])}"

        gh_ms = sun.get("golden_hour_morning_start")
        gh_es = sun.get("golden_hour_evening_start")
        gh_ee = sun.get("golden_hour_evening_end")
        if gh_ms and gh_es and gh_ee:
            golden_str = (
                f"AM {gh_ms.strftime('%H:%M')} / "
                f"PM {gh_es.strftime('%H:%M')}–{gh_ee.strftime('%H:%M')}"
            )
        else:
            golden_str = "—"

        table.add_row(
            f"#{rank}",
            _fmt_elev(peak["elevation_m"]),
            _fmt_score(peak["score_km2"]),
            th_dist,
            gain_str,
            weather_str,
            golden_str,
        )

    console.print(table)

    # ── Detailed top peak ───────────────────────────────────────────────────
    if enriched_peaks:
        _print_detailed_peak(enriched_peaks[0])

    # ── Footnote ────────────────────────────────────────────────────────────
    rprint(
        f"\n[dim]Viewshed scores account for Earth curvature and terrain blocking. "
        f"Max ray distance: {args.max_dist:.0f} km.[/dim]"
    )

    # ── HTML map ────────────────────────────────────────────────────────────
    if not args.no_map:
        rprint("\n[bold]Generating HTML map…[/bold]")
        map_path = generate_map(
            center_lat=center_lat,
            center_lon=center_lon,
            radius_km=args.radius,
            peaks_with_scores=enriched_peaks,
            output_path=args.output,
        )
        rprint(f"[green]Map saved:[/green] {map_path}")
        try:
            import os
            os.startfile(map_path)
        except Exception:
            try:
                webbrowser.open(f"file:///{map_path}")
            except Exception:
                pass


if __name__ == "__main__":
    main()
