# 🗺️ Geospatial Backend: Fog & Peak Finder

This repository contains the Python backend for two distinct geospatial analysis tools: **Fog Finder** and **Peak Finder**. It handles complex environmental modeling, elevation processing, weather data integration, and map visualization. The backend is designed to be executed via **Modal** for scalable, serverless deployment.

---

## 🏗 Architecture & Modules

The backend is split into two primary micro-services, each with its own specific domain logic and output generation.

### 🌫️ 1. Fog Finder (`/fog_finder`)
A predictive modeling and visualization tool for tracking and mapping fog conditions.
* `fog_model.py`: Core logic/algorithm for predicting fog density and movement.
* `weather.py`: Integrates external weather APIs to feed meteorological data into the model.
* `map_viz.py`: Generates the geospatial visualization.
* `fog_map.html`: The automated output map rendering the fog data.

### ⛰️ 2. Peak Finder (`/peak_finder`)
A comprehensive terrain and hiking analysis engine.
* `peaks.py` & `elevation.py`: Identifies topographic prominence and processes elevation data.
* `viewshed.py`: Calculates the theoretical line-of-sight/visible area from specific peaks.
* `sun_analysis.py`: Models solar exposure and shadows across the terrain.
* `trailheads.py` & `weather.py`: Maps accessible starting points and fetches localized mountain weather.
* `map_output.py`: Compiles the analysis into `peak_finder_results.html`.

### 🚀 3. Deployment (`modal_app.py`)
The root directory contains `modal_app.py`, which utilizes [Modal](https://modal.com/) to containerize and deploy these Python scripts to the cloud, allowing for heavy geospatial processing without taxing local hardware.

---

## 🛠️ Tech Stack (Inferred)
* **Language:** Python
* **Deployment/Compute:** Modal (`modal_app.py`)
* **Visualization:** HTML/JS Map outputs (likely Folium/Leaflet)
* **Environment:** Virtual Environments (`venv` / `.venv`)

---

## 💻 Local Setup & Development

### 1. Initialize the Environment
It is recommended to use a virtual environment to avoid dependency conflicts.
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\Scripts\activate