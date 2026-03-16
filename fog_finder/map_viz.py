import folium
from folium.plugins import HeatMapWithTime
import numpy as np


def fmt_time(t):
    """'2026-03-13T06:00' → '2026-03-13  6:00 AM'"""
    h = int(t[11:13])
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{t[:10]}  {h12}:00 {suffix}"


def nearest_grid_point(lat, lon, grid):
    """Return the grid point closest to (lat, lon)."""
    best = min(grid, key=lambda p: (p["lat"] - lat) ** 2 + (p["lon"] - lon) ** 2)
    return best


def spot_status(spot_elev, fog_base_asl, fog_top_asl, fog_score):
    """
    Returns (icon, label, detail) describing the relationship between the
    shooting spot and the fog layer.

    'Sweet spot' is when the fog top is within 0–150 m below the viewpoint —
    you can look down into a sea of clouds from just above the layer.
    """
    if fog_score < 0.15:
        return "🌤", "Clear", f"low fog ({fog_score:.0%})"

    margin = spot_elev - fog_top_asl   # positive → above fog top

    if margin > 150:
        return "⬆️", "Above fog", f"{margin:.0f} m above layer top ({fog_top_asl:.0f} m)"
    elif 0 <= margin <= 150:
        return "✨", "SWEET SPOT", f"{margin:.0f} m above fog top — shoot now!"
    elif fog_base_asl <= spot_elev < fog_top_asl:
        return "☁️", "In fog", f"inside layer ({fog_base_asl:.0f}–{fog_top_asl:.0f} m)"
    else:
        return "⬇️", "Below fog", f"fog base at {fog_base_asl:.0f} m ASL"


def spot_popup_html(spot, nearest, times):
    """Build an HTML popup table for a favourite shooting spot."""
    name  = spot["name"]
    elev  = spot.get("elevation") or nearest["elevation"]
    rows  = []

    for i, t in enumerate(times):
        hour = int(t[11:13])
        # Show only hours where there's meaningful fog, or the dawn window
        fscore = nearest["fog_scores"][i]
        if fscore < 0.15 and not (3 <= hour <= 10):
            continue

        base  = nearest["fog_base_asl"][i]
        top   = nearest["fog_top_asl"][i]
        icon, label, detail = spot_status(elev, base, top, fscore)

        # Highlight sweet spots
        bg = "#fffde7" if label == "SWEET SPOT" else ("" if i % 2 == 0 else "#f9f9f9")
        rows.append(
            f'<tr style="background:{bg}">'
            f'<td style="padding:2px 6px;white-space:nowrap">{fmt_time(t)}</td>'
            f'<td style="padding:2px 6px">{icon} {label}</td>'
            f'<td style="padding:2px 4px;color:#555;font-size:11px">{detail}</td>'
            f'</tr>'
        )

    if not rows:
        rows = ['<tr><td colspan="3" style="padding:6px;color:#888">No significant fog forecast</td></tr>']

    table = (
        '<table style="border-collapse:collapse;font-family:sans-serif;font-size:12px">'
        '<thead><tr style="background:#eee">'
        '<th style="padding:3px 6px;text-align:left">Time</th>'
        '<th style="padding:3px 6px;text-align:left">Status</th>'
        '<th style="padding:3px 6px;text-align:left">Detail</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )

    return (
        f'<div style="font-family:sans-serif">'
        f'<b style="font-size:14px">📍 {name}</b><br>'
        f'<span style="color:#555;font-size:12px">Your elevation: <b>{elev:.0f} m</b> ASL</span>'
        f'<br><br>'
        f'{table}'
        f'<br><small style="color:#999">✨ = fog top just below you — perfect for sea-of-clouds shots</small>'
        f'</div>'
    )


def best_viewpoints(grid, top_n=5):
    candidates = []
    for point in grid:
        max_fog = max(point["fog_scores"])
        score = point["elevation"] * max_fog * (1 - point["valley_score"] * 0.5)
        candidates.append((score, point))
    candidates.sort(reverse=True, key=lambda x: x[0])
    return [p for _, p in candidates[:top_n]]


def create_map(fog_data, favorite_spots=None, output_file="fog_map.html"):
    times = fog_data["times"]
    grid  = fog_data["grid"]
    if favorite_spots is None:
        favorite_spots = []

    center_lat = np.mean([p["lat"] for p in grid])
    center_lon = np.mean([p["lon"] for p in grid])

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles="CartoDB positron",
    )

    # ── Fog probability heatmap ───────────────────────────────────────────────
    heatmap_data = []
    for i in range(len(times)):
        frame = [
            [p["lat"], p["lon"], p["fog_scores"][i]]
            for p in grid
            if p["fog_scores"][i] > 0.05
        ]
        heatmap_data.append(frame)

    time_labels = [fmt_time(t) for t in times]

    HeatMapWithTime(
        heatmap_data,
        index=time_labels,
        auto_play=False,
        max_opacity=0.85,
        min_opacity=0.0,
        radius=30,
        gradient={
            "0.0": "blue",
            "0.4": "cyan",
            "0.65": "lime",
            "0.8": "yellow",
            "1.0": "red",
        },
        name="Fog Probability",
    ).add_to(m)

    # ── Fog ceiling height heatmap (separate layer) ───────────────────────────
    # Weight = fog_top_asl normalised; only shown when fog is likely.
    # Brighter = higher fog ceiling — tells you how tall the fog layer is.
    all_tops = [t for p in grid for t in p["fog_top_asl"]]
    max_top  = max(all_tops) if all_tops else 1000

    ceiling_data = []
    for i in range(len(times)):
        frame = []
        for p in grid:
            if p["fog_scores"][i] > 0.2:
                weight = p["fog_top_asl"][i] / max_top
                frame.append([p["lat"], p["lon"], weight])
        ceiling_data.append(frame)

    HeatMapWithTime(
        ceiling_data,
        index=time_labels,
        auto_play=False,
        max_opacity=0.75,
        min_opacity=0.0,
        radius=30,
        gradient={
            "0.0": "#4a0080",
            "0.4": "#0000ff",
            "0.65": "#00aaff",
            "0.85": "#00ffcc",
            "1.0": "#ffffff",
        },
        name="Fog Ceiling Height",
    ).add_to(m)

    # ── Auto-detected viewpoints ──────────────────────────────────────────────
    vp_group = folium.FeatureGroup(name="Suggested Viewpoints")
    for i, vp in enumerate(best_viewpoints(grid)):
        peak_idx   = int(np.argmax(vp["fog_scores"]))
        peak_time  = fmt_time(times[peak_idx])
        peak_score = vp["fog_scores"][peak_idx]
        fog_top    = vp["fog_top_asl"][peak_idx]
        margin     = vp["elevation"] - fog_top

        _, status, detail = spot_status(
            vp["elevation"],
            vp["fog_base_asl"][peak_idx],
            fog_top,
            peak_score,
        )

        folium.Marker(
            location=[vp["lat"], vp["lon"]],
            popup=folium.Popup(
                f"<b>Auto Viewpoint #{i + 1}</b><br>"
                f"Elevation: {vp['elevation']:.0f} m ASL<br>"
                f"Peak fog: {peak_score:.0%} at {peak_time}<br>"
                f"Fog top at peak: {fog_top:.0f} m ASL<br>"
                f"Status: {status} ({detail})",
                max_width=260,
            ),
            icon=folium.Icon(color="red", icon="camera", prefix="fa"),
            tooltip=f"📷 Viewpoint #{i + 1} — {status} at peak",
        ).add_to(vp_group)
    vp_group.add_to(m)

    # ── Favourite shooting spots ──────────────────────────────────────────────
    if favorite_spots:
        spots_group = folium.FeatureGroup(name="My Shooting Spots")
        for spot in favorite_spots:
            nearest = nearest_grid_point(spot["lat"], spot["lon"], grid)
            elev    = spot.get("elevation") or nearest["elevation"]

            # Find the best (sweet-spot) hour for this location
            sweet_times = []
            for i, t in enumerate(times):
                _, label, _ = spot_status(
                    elev,
                    nearest["fog_base_asl"][i],
                    nearest["fog_top_asl"][i],
                    nearest["fog_scores"][i],
                )
                if label == "SWEET SPOT":
                    sweet_times.append(fmt_time(t))

            tooltip_extra = f" — sweet spot at {sweet_times[0]}" if sweet_times else " — no sweet spot forecast"

            folium.Marker(
                location=[spot["lat"], spot["lon"]],
                popup=folium.Popup(
                    spot_popup_html(spot, nearest, times),
                    max_width=480,
                ),
                icon=folium.Icon(color="purple", icon="star", prefix="fa"),
                tooltip=f"⭐ {spot['name']} ({elev:.0f} m){tooltip_extra}",
            ).add_to(spots_group)
        spots_group.add_to(m)

    # ── Grid elevation overlay (hidden by default) ────────────────────────────
    elev_group = folium.FeatureGroup(name="Grid Points (elevation)", show=False)
    for p in grid:
        avg_top = int(np.mean(p["fog_top_asl"]))
        folium.CircleMarker(
            location=[p["lat"], p["lon"]],
            radius=4,
            color="gray",
            fill=True,
            fill_opacity=0.5,
            tooltip=(
                f"Elev: {p['elevation']:.0f} m  |  "
                f"Valley: {p['valley_score']:.2f}  |  "
                f"Avg fog top: {avg_top} m ASL"
            ),
        ).add_to(elev_group)
    elev_group.add_to(m)

    folium.LayerControl().add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────────
    spots_note = (
        '<span style="color:purple">⭐</span> Your shooting spots (click for hourly status)<br>'
        if favorite_spots else
        '<small style="color:#aaa">Add spots to FAVORITE_SPOTS in config.py</small><br>'
    )
    legend_html = f"""
    <div style="
        position: fixed; bottom: 30px; right: 30px; z-index: 9999;
        background: white; padding: 14px 18px; border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
        font-family: sans-serif; font-size: 13px; line-height: 1.8;
    ">
        <b style="font-size:14px">🌫 Fog Probability</b><br>
        <span style="color:#00f">■</span> Low (&lt;40%)<br>
        <span style="color:#0ff">■</span> Moderate (40–65%)<br>
        <span style="color:#0f0">■</span> High (65–80%)<br>
        <span style="color:#ff0">■</span> Very High (80–90%)<br>
        <span style="color:#f00">■</span> Extreme (&gt;90%)<br>
        <hr style="margin:6px 0; border-color:#eee">
        <b style="font-size:13px">☁️ Fog Ceiling layer</b><br>
        <small style="color:#666">White = high ceiling, purple = low<br>
        Toggle in layers panel (top-right)</small><br>
        <hr style="margin:6px 0; border-color:#eee">
        <span style="color:red">📷</span> Auto-detected viewpoints<br>
        {spots_note}
        <small style="color:#888">✨ Sweet spot = fog top just below you</small>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save(output_file)
    print(f"  Saved: {output_file}")
    return output_file
