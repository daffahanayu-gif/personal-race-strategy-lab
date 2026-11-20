import gpxpy
import pandas as pd
import numpy as np
import requests 
from datetime import datetime, timedelta

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlambda/2)**2
    return 2 * R * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

def parse_gpx_data(gpx_bytes):
    gpx = gpxpy.parse(gpx_bytes.decode("utf-8"))
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                points.append({
                    'lat': p.latitude,
                    'lon': p.longitude,
                    'ele': p.elevation if p.elevation is not None else 0.0
                })
    df = pd.DataFrame(points)
    df['ele_smooth'] = df['ele'].rolling(window=5, min_periods=1, center=True).mean()
    df['dist_step_m'] = haversine(df['lat'].shift(1), df['lon'].shift(1), df['lat'], df['lon']).fillna(0)
    df['distance_km'] = df['dist_step_m'].cumsum() / 1000.0
    
    df['ele_diff'] = df['ele_smooth'].diff().fillna(0)
    df['ele_gain'] = df['ele_diff'].apply(lambda x: x if x > 0 else 0)
    df['ele_loss'] = df['ele_diff'].apply(lambda x: abs(x) if x < 0 else 0)
    
    df['gradient_pct'] = np.where(df['dist_step_m'] > 1, (df['ele_diff'] / df['dist_step_m']) * 100, 0)
    df['gradient_pct'] = df['gradient_pct'].clip(-45, 45)
    
    def classify_zone(g):
        if g > 15: return '1. Tanjakan Ekstrem (>15%)'
        elif g > 5: return '2. Tanjakan Sedang (5-15%)'
        elif g >= -5: return '3. Datar / Nabung Waktu (-5% s/d 5%)'
        elif g >= -15: return '4. Turunan Landai (-15% s/d -5%)'
        else: return '5. Turunan Curam / Quad-Killer (<-15%)'
        
    df['terrain_zone'] = df['gradient_pct'].apply(classify_zone)
    return df

def run_strategy_simulation(df_raw, jam_start_str, target_durasi_jam, ws_input_str, mode_strategi):
    df = df_raw.copy()
    
    def effort_multiplier(g):
        if g > 15: return 2.4
        elif g > 5: return 1.5
        elif g >= -5: return 1.0
        elif g >= -15: return 0.9
        else: return 1.3

    df['effort_units'] = df['dist_step_m'] * df['gradient_pct'].apply(effort_multiplier)
    total_km = float(df['distance_km'].max())
    progress = df['distance_km'] / total_km
    
    if "Konservatif" in mode_strategi:
        df['effort_units'] *= np.where(progress < 0.5, 1.1, 0.9)
    elif "Agresif" in mode_strategi:
        df['effort_units'] *= np.where(progress < 0.5, 0.9, 1.1)

    total_effort = df['effort_units'].sum()
    total_seconds = target_durasi_jam * 3600

    df['step_seconds'] = (df['effort_units'] / total_effort) * total_seconds
    df['cum_seconds'] = df['step_seconds'].cumsum()

    start_dt = datetime.strptime(jam_start_str, "%H:%M")
    df['est_time'] = df['cum_seconds'].apply(lambda s: (start_dt + timedelta(seconds=float(s))).strftime("%H:%M"))

    # Penentuan Pos/WS Otomatis vs Manual (Bersih dengan tipe float standar)
    if ws_input_str.strip() == "" or ws_input_str.strip().upper() == "AUTO":
        if total_km < 12: num_ws = 1
        elif total_km < 22: num_ws = 2
        elif total_km < 35: num_ws = 3
        else: num_ws = max(3, int(total_km // 10))
        
        ws_list = []
        for i in range(1, num_ws + 1):
            target_sec = (total_seconds / (num_ws + 1)) * i
            idx_ws = (df['cum_seconds'] - target_sec).abs().idxmin()
            km_found = round(float(df.loc[idx_ws, 'distance_km']), 1)
            if 1.0 < km_found < (total_km - 1.0):
                ws_list.append(km_found)
        ws_list = sorted(list(set(ws_list)))
        ws_label_str = ", ".join([f"KM {x}" for x in ws_list])
        ws_mode = f"WS Auto: {ws_label_str}"
    else:
        ws_list = [round(float(x.strip()), 1) for x in ws_input_str.split(",") if x.strip() != ""]
        ws_label_str = ", ".join([f"KM {x}" for x in ws_list])
        ws_mode = f"WS Manual: {ws_label_str}"

    return df, ws_list, ws_mode

def fetch_terrain_surface(df, grid_size=45):
    """Mengambil grid elevasi DEM resolusi tinggi di sekitar lintasan untuk membentuk maket gunung 3D padat."""
    pad_lat = (df['lat'].max() - df['lat'].min()) * 0.22 + 0.003
    pad_lon = (df['lon'].max() - df['lon'].min()) * 0.22 + 0.003

    lats = np.linspace(df['lat'].min() - pad_lat, df['lat'].max() + pad_lat, grid_size)
    lons = np.linspace(df['lon'].min() - pad_lon, df['lon'].max() + pad_lon, grid_size)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    flat_lats = lat_grid.ravel()
    flat_lons = lon_grid.ravel()

    try:
        elevs = []
        chunk_size = 100
        for i in range(0, len(flat_lats), chunk_size):
            lat_str = ",".join([f"{x:.5f}" for x in flat_lats[i:i+chunk_size]])
            lon_str = ",".join([f"{x:.5f}" for x in flat_lons[i:i+chunk_size]])
            url = f"https://api.open-meteo.com/v1/elevation?latitude={lat_str}&longitude={lon_str}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            elevs.extend(resp.json()["elevation"])
        z_grid = np.array(elevs).reshape(lat_grid.shape)
        return lon_grid, lat_grid, z_grid
    except Exception:
        return None, None, None