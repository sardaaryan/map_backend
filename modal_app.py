import modal
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import numpy as np

# --- 1. Import your custom functions ---
from peak_finder.elevation import get_dem
from peak_finder.peaks import find_peaks
from peak_finder.viewshed import compute_viewshed_score
from fog_finder.weather import fetch_grid
from fog_finder.fog_model import compute_fog_grid

#Image with all dependencies and your local code 
image = (
    modal.Image.debian_slim()
    .pip_install(
        "numpy", 
        "scipy", 
        "requests", 
        "astral", 
        "timezonefinder", 
        "fastapi",
        "rich",
        "pyproj",
        "timezonefinder", 
        "fastapi"
    )
    .add_local_python_source("peak_finder")
    .add_local_python_source("fog_finder")
)

# Create the Modal App and the FastAPI web app
app = modal.App("peak-and-fog-backend")
web_app = FastAPI(title="Peak & Fog Finder API")

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://map-frontend-xi.vercel.app"],  # Allows all websites to talk to your API (great for testing)
    allow_credentials=True,
    allow_methods=["*"],  # Allows GET, POST, OPTIONS, etc.
    allow_headers=["*"],
)

# --- 2. The Fog Finder Endpoint ---
@web_app.get("/api/find-fog")
def api_find_fog(
    lat_min: float, lat_max: float, 
    lon_min: float, lon_max: float, 
    grid: int = 10, days: int = 3
):
    """Calculates the valley fog probabilities for a bounding box."""
    # Build the grid points (copied from your fog_finder main.py)
    lats = np.linspace(lat_min, lat_max, grid)
    lons = np.linspace(lon_min, lon_max, grid)
    grid_points = [(float(lat), float(lon)) for lat in lats for lon in lons]

    # Fetch weather and compute fog
    weather_data = fetch_grid(grid_points, forecast_days=days, max_workers=5)
    fog_data = compute_fog_grid(weather_data)
    
    return {"status": "success", "data": fog_data}


# --- 3. The Peak Finder Endpoint ---
@web_app.get("/api/find-peaks")
def api_find_peaks(lat: float, lon: float, radius: float = 30.0):
    """Finds peaks and calculates viewsheds around a center point."""
    # Get Elevation Data
    dem, lats, lons, pixel_size_m = get_dem(lat, lon, radius_km=radius)
    
    # Find Peaks
    peaks = find_peaks(dem, lats, lons, lat, lon, radius)
    
    # Calculate Viewshed for the top 10 peaks (to keep web response times fast)
    results = []
    for peak in peaks[:10]:
        score = compute_viewshed_score(
            dem=dem, 
            center_row=peak['row'], 
            center_col=peak['col'], 
            pixel_size_m=pixel_size_m,   # Approx 30m resolution for SRTM1
            max_dist_m=30000.0   # 30km max view distance
        )
        
        # Convert NumPy types to standard Python floats so FastAPI can return JSON
        peak['viewshed_score'] = float(score)
        peak['lat'] = float(peak['lat'])
        peak['lon'] = float(peak['lon'])
        peak['elevation_m'] = float(peak['elevation_m'])
        results.append(peak)
        
    return {"status": "success", "peaks": results}


# --- 4. Bind the FastAPI app to Modal ---
@app.function(image=image, memory=4096, cpu=2.0)
@modal.asgi_app()
def fastapi_app():
    return web_app