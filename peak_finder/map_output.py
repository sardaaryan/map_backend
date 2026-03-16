"""
Folium HTML map generation for peak_finder results.
"""

import datetime
from pathlib import Path
from typing import Optional

import folium
from folium import Element

try:
    from .utils import compass_dir
except ImportError:
    from utils import compass_dir  # type: ignore[no-redef]


# Rank → marker colour
RANK_COLORS = {
    1: "orange",
    2: "lightgray",
    3: "beige",
}
DEFAULT_COLOR = "lightblue"


def _fmt_time(dt: Optional[datetime.datetime]) -> str:
    """Format a UTC datetime as HH:MM UTC, or '—' if None."""
    if dt is None:
        return "—"
    return dt.strftime("%H:%M UTC")


def _fmt_azimuth(az: Optional[float]) -> str:
    """Format an azimuth value with compass direction, or '—' if None."""
    if az is None:
        return "—"
    return f"{az:.0f}° ({compass_dir(az)})"


def _build_popup_html(peak: dict) -> str:
    """Build a rich HTML popup string for a peak marker."""
    rank = peak.get("rank", "?")
    lat = peak.get("lat", 0.0)
    lon = peak.get("lon", 0.0)
    elev = peak.get("elevation_m", 0.0)
    score = peak.get("score_km2", 0.0)
    trailhead = peak.get("trailhead")
    elev_gain = peak.get("elevation_gain_m")
    weather = peak.get("weather", {}) or {}
    sun_info = peak.get("sun_info", {}) or {}

    # Trailhead info
    if trailhead:
        th_name = trailhead.get("name", "Unknown")
        th_dist_km = trailhead.get("distance_km", 0.0)
        th_dist_mi = th_dist_km * 0.621371
        trailhead_str = f"{th_name} ({th_dist_mi:.1f} mi / {th_dist_km:.1f} km)"
    else:
        trailhead_str = "None found"

    # Elevation gain
    if elev_gain is not None:
        gain_ft = elev_gain * 3.28084
        gain_str = f"{gain_ft:,.0f} ft ({elev_gain:,.0f} m)"
    else:
        gain_str = "—"

    # Weather
    weather_desc = weather.get("description", "unavailable")
    cloud = weather.get("cloud_cover_pct")
    clear = weather.get("clear_chance_pct")
    temp = weather.get("temperature_c")
    vis = weather.get("visibility_m")

    weather_lines = [f"<b>Conditions:</b> {weather_desc}"]
    if cloud is not None:
        weather_lines.append(f"<b>Cloud cover:</b> {cloud}%  |  <b>Clear chance:</b> {clear}%")
    if temp is not None:
        temp_f = temp * 9 / 5 + 32
        weather_lines.append(f"<b>Temperature:</b> {temp_f:.0f} °F ({temp:.1f} °C)")
    if vis is not None:
        vis_mi = vis / 1609.34
        weather_lines.append(f"<b>Visibility:</b> {vis_mi:.1f} mi ({vis/1000:.1f} km)")

    # Sun info
    sunrise = _fmt_time(sun_info.get("sunrise_utc"))
    sunset = _fmt_time(sun_info.get("sunset_utc"))
    gh_m_start = _fmt_time(sun_info.get("golden_hour_morning_start"))
    gh_m_end = _fmt_time(sun_info.get("golden_hour_morning_end"))
    gh_e_start = _fmt_time(sun_info.get("golden_hour_evening_start"))
    gh_e_end = _fmt_time(sun_info.get("golden_hour_evening_end"))
    gh_m_az = _fmt_azimuth(sun_info.get("golden_hour_morning_azimuth"))
    gh_e_az = _fmt_azimuth(sun_info.get("golden_hour_evening_azimuth"))
    best_months = sun_info.get("best_months", "—")

    elev_ft = elev * 3.28084
    score_mi2 = score * 0.386102
    popup_html = f"""
<div style="font-family: Arial, sans-serif; min-width: 280px; max-width: 340px;">
  <h3 style="margin:0 0 6px 0; color:#c0392b;">
    #{rank} &mdash; {elev_ft:,.0f} ft ({elev:,.0f} m)
  </h3>
  <table style="border-collapse:collapse; width:100%; font-size:13px;">
    <tr><td style="padding:2px 6px;"><b>Coords:</b></td>
        <td style="padding:2px 6px;">{lat:.4f}°, {lon:.4f}°</td></tr>
    <tr style="background:#f5f5f5;"><td style="padding:2px 6px;"><b>Viewshed score:</b></td>
        <td style="padding:2px 6px;">{score_mi2:.0f} mi² ({score:.0f} km²)</td></tr>
    <tr><td style="padding:2px 6px;"><b>Nearest trailhead:</b></td>
        <td style="padding:2px 6px;">{trailhead_str}</td></tr>
    <tr style="background:#f5f5f5;"><td style="padding:2px 6px;"><b>Elevation gain:</b></td>
        <td style="padding:2px 6px;">{gain_str}</td></tr>
  </table>

  <hr style="margin:8px 0; border:none; border-top:1px solid #ddd;"/>
  <b style="font-size:13px;">Weather (current):</b>
  <div style="font-size:12px; margin:4px 0;">
    {"<br/>".join(weather_lines)}
  </div>

  <hr style="margin:8px 0; border:none; border-top:1px solid #ddd;"/>
  <b style="font-size:13px;">Sun &amp; Golden Hour (UTC):</b>
  <div style="font-size:12px; margin:4px 0;">
    <b>Sunrise:</b> {sunrise} &nbsp;|&nbsp; <b>Sunset:</b> {sunset}<br/>
    <b>Morning golden hour:</b> {gh_m_start} – {gh_m_end} &nbsp;(sun at {gh_m_az})<br/>
    <b>Evening golden hour:</b> {gh_e_start} – {gh_e_end} &nbsp;(sun at {gh_e_az})<br/>
    <b>Best months:</b> {best_months}
  </div>
</div>
"""
    return popup_html


LEGEND_HTML = """
<div style="
    position: fixed;
    bottom: 30px; right: 15px; z-index: 1000;
    background: white; border:2px solid #aaa; border-radius:8px;
    padding: 12px 16px; font-family: Arial, sans-serif; font-size: 13px;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.3);
    max-width: 220px;
">
  <b style="font-size:14px;">Peak Finder Legend</b><br/><br/>
  <span style="color:#e67e22;">&#9679;</span> <b>#1</b> Best viewshed<br/>
  <span style="color:#95a5a6;">&#9679;</span> <b>#2</b> Second best<br/>
  <span style="color:#f5cba7;">&#9679;</span> <b>#3</b> Third best<br/>
  <span style="color:#5dade2;">&#9679;</span> Other top peaks<br/>
  <span style="color:#2980b9;">&#9679;</span> Search centre<br/><br/>
  <hr style="border:none; border-top:1px solid #eee; margin:6px 0;"/>
  <b>Viewshed score</b> = visible area<br/>
  in mi² (km²) from each peak summit.<br/>
  Accounts for terrain blocking<br/>
  and Earth curvature.
</div>
"""


def generate_map(
    center_lat: float,
    center_lon: float,
    radius_km: float,
    peaks_with_scores: list[dict],
    output_path: str = "peak_finder_results.html",
) -> str:
    """
    Generate a Folium HTML map showing ranked peaks and the search area.

    Args:
        center_lat:        Center latitude of the search.
        center_lon:        Center longitude of the search.
        radius_km:         Search radius in km (drawn as a circle).
        peaks_with_scores: List of peak dicts (must include rank, score_km2, etc.).
        output_path:       Where to save the HTML file.

    Returns:
        Absolute path to the saved HTML file (as string).
    """
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="OpenStreetMap",
    )

    # Search radius circle
    folium.Circle(
        location=[center_lat, center_lon],
        radius=radius_km * 1000,
        color="#2980b9",
        fill=True,
        fill_color="#2980b9",
        fill_opacity=0.05,
        weight=2,
        tooltip=f"Search radius: {radius_km:.0f} km",
    ).add_to(m)

    # Centre marker
    folium.Marker(
        location=[center_lat, center_lon],
        tooltip="Search centre",
        popup=folium.Popup(
            f"<b>Search centre</b><br/>{center_lat:.4f}°, {center_lon:.4f}°<br/>"
            f"Radius: {radius_km:.0f} km",
            max_width=200,
        ),
        icon=folium.Icon(color="blue", icon="crosshairs", prefix="fa"),
    ).add_to(m)

    # Peak markers
    for peak in peaks_with_scores:
        rank = peak.get("rank", 99)
        color = RANK_COLORS.get(rank, DEFAULT_COLOR)
        elev = peak.get("elevation_m", 0.0)
        score = peak.get("score_km2", 0.0)
        name = peak.get("name") or "Unnamed Peak"
        elev_ft = elev * 3.28084
        score_mi2 = score * 0.386102
        tooltip_text = f"#{rank}. {name} — {elev_ft:,.0f} ft | {score_mi2:.0f} mi² view"

        popup_html = _build_popup_html(peak)

        folium.Marker(
            location=[peak["lat"], peak["lon"]],
            tooltip=tooltip_text,
            popup=folium.Popup(popup_html, max_width=360),
            icon=folium.Icon(color=color, icon="mountain", prefix="fa"),
        ).add_to(m)

    # Inject legend HTML
    legend_element = Element(LEGEND_HTML)
    m.get_root().html.add_child(legend_element)

    # Save
    output = Path(output_path)
    m.save(str(output))
    return str(output.resolve())
