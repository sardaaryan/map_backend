import numpy as np


def fog_score(humidity, dp_spread, wind_speed, cloud_cover, is_dawn):
    """
    Returns fog probability 0.0–1.0.

    humidity     : relative humidity %
    dp_spread    : temperature - dewpoint (°C). Lower = closer to saturation.
    wind_speed   : wind speed kph. High wind disperses fog.
    cloud_cover  : % cloud cover. Clear sky enables radiative cooling.
    is_dawn      : True between 3–9 AM local time (golden photo window).
    """
    h  = np.clip((humidity - 70) / 30, 0, 1)        # 70% → 0, 100% → 1
    dp = np.clip(1 - dp_spread / 5,   0, 1)        # 0°C → 1, 5°C → 0
    w  = np.clip(1 - wind_speed / 15,  0, 1)        # 0 kph → 1, 15 kph → 0
    c  = np.clip(1 - cloud_cover / 100, 0, 1)       # clear sky bonus

    score = h * 0.35 + dp * 0.35 + w * 0.20 + c * 0.10

    if is_dawn:
        score *= 1.2   # fog most visible at dawn / early morning

    return float(np.clip(score, 0, 1))


def valley_scores(elevations):
    """
    Score each grid point by how much lower it is than its neighbours.
    Valley bottoms (cold-air pooling) score highest (0–1).
    """
    elevations = np.array(elevations, dtype=float)
    mean_elev = np.mean(elevations)
    std_elev   = np.std(elevations) if np.std(elevations) > 0 else 1.0
    scores = np.clip((mean_elev - elevations) / (std_elev + 1), 0, None)
    if scores.max() > 0:
        scores /= scores.max()
    return scores.tolist()


def fog_ceiling(temp_c, dewpoint_c, ground_elev_m, blh_m):
    """
    Returns (fog_base_asl, fog_top_asl) in metres above sea level.

    fog_base: LCL formula — 125 m per 1°C of dewpoint depression.
              Near 0 when temp ≈ dewpoint (saturated surface air = dense valley fog).
    fog_top : ground elevation + boundary layer height when BLH data is available,
              otherwise fog_base + 300 m as a rough fallback.
    """
    lcl_agl      = 125.0 * max(0.0, temp_c - dewpoint_c)   # metres AGL
    fog_base_asl = ground_elev_m + lcl_agl

    if blh_m is not None and blh_m > 0:
        fog_top_asl = ground_elev_m + blh_m
    else:
        fog_top_asl = fog_base_asl + 300.0

    # Fog top should be at least as high as base
    fog_top_asl = max(fog_top_asl, fog_base_asl + 50.0)
    return round(fog_base_asl), round(fog_top_asl)


def compute_fog_grid(weather_data):
    """
    Accepts list of point dicts from weather.py.
    Returns dict:
        times : list of ISO time strings
        grid  : list of point dicts, each with:
                  fog_scores       – fog probability per hour (0–1)
                  fog_base_asl     – estimated fog base elevation ASL per hour (m)
                  fog_top_asl      – estimated fog top elevation ASL per hour (m)
    """
    if not weather_data:
        return {}

    times = weather_data[0]["hourly"]["time"]
    elevations = [p["elevation"] for p in weather_data]
    v_scores = valley_scores(elevations)

    grid = []
    for point, v_score in zip(weather_data, v_scores):
        h = point["hourly"]
        scores, bases, tops = [], [], []

        for i, t in enumerate(times):
            hour = int(t[11:13])
            is_dawn = 3 <= hour <= 9

            def safe(key, fallback=0):
                col = h.get(key, [])
                return col[i] if i < len(col) and col[i] is not None else fallback

            hum   = safe("relativehumidity_2m", 50)
            temp  = safe("temperature_2m",       15)
            dew   = safe("dewpoint_2m",          10)
            wind  = safe("windspeed_10m",        10)
            cloud = safe("cloudcover",           50)
            blh   = safe("boundary_layer_height", None)

            dp_sp = temp - dew
            base  = fog_score(hum, dp_sp, wind, cloud, is_dawn)
            final = min(1.0, base + v_score * 0.15)
            scores.append(round(final, 3))

            fb, ft = fog_ceiling(temp, dew, point["elevation"], blh)
            bases.append(fb)
            tops.append(ft)

        grid.append({
            "lat":          point["lat"],
            "lon":          point["lon"],
            "elevation":    point["elevation"],
            "valley_score": v_score,
            "fog_scores":   scores,
            "fog_base_asl": bases,
            "fog_top_asl":  tops,
            "daily":        point["daily"],
        })

    return {"times": times, "grid": grid}
