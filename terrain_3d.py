import numpy as np
import plotly.graph_objects as go
from scipy.interpolate import griddata

def build_3d_terrain_figure(df, ws_list, jam_start, est_finish, color_dict):
    total_km = float(df['distance_km'].max())
    
    # 1. Bentuk Grid Permukaan Gunung Padat Secara Instan (Bebas Timeout API)
    grid_size = 45
    pad_lat = (df['lat'].max() - df['lat'].min()) * 0.22 + 0.0025
    pad_lon = (df['lon'].max() - df['lon'].min()) * 0.22 + 0.0025

    lats = np.linspace(df['lat'].min() - pad_lat, df['lat'].max() + pad_lat, grid_size)
    lons = np.linspace(df['lon'].min() - pad_lon, df['lon'].max() + pad_lon, grid_size)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    pts = df[['lon', 'lat']].values
    vals = df['ele_smooth'].values
    z_linear = griddata(pts, vals, (lon_grid, lat_grid), method='linear')
    z_nearest = griddata(pts, vals, (lon_grid, lat_grid), method='nearest')
    
    # Buat lereng alami menurun ke tepi luar diorama
    dist_to_track = np.min(
        np.sqrt((lon_grid[..., None] - pts[:, 0])**2 + (lat_grid[..., None] - pts[:, 1])**2),
        axis=-1
    )
    slope_drop = (dist_to_track / (np.max(dist_to_track) + 1e-9)) * 90.0
    z_grid = np.where(np.isnan(z_linear), z_nearest - slope_drop, z_linear)

    fig3d = go.Figure()

    # 2. Permukaan Atas Gunung Padat (Realistic Earth + Hillshade Lighting)
    realistic_earth_scale = [
        [0.0, '#4a6b48'],
        [0.25, '#7c8c58'],
        [0.50, '#b5a273'],
        [0.75, '#967c54'],
        [1.0, '#d6cbb5']
    ]
    fig3d.add_trace(go.Surface(
        x=lon_grid, y=lat_grid, z=z_grid,
        colorscale=realistic_earth_scale,
        opacity=1.0,
        showscale=False,
        lighting=dict(ambient=0.45, diffuse=0.85, specular=0.15, roughness=0.85, fresnel=0.1),
        lightposition=dict(x=100, y=200, z=500),
        contours=dict(z=dict(show=True, color='rgba(60, 45, 30, 0.28)', width=1)),
        hoverinfo='skip',
        name='Kontur Bukit 3D'
    ))

    # 3. Dinding Penutup Samping & Alas Bawah (Terrain Skirt / Balok Diorama Padat)
    z_base = float(np.nanmin(z_grid)) - 55
    skirt_color = [[0, '#2b2d30'], [1, '#3f4246']]
    edges = [
        (lon_grid[0, :],  lat_grid[0, :],  z_grid[0, :]),
        (lon_grid[-1, :], lat_grid[-1, :], z_grid[-1, :]),
        (lon_grid[:, 0],  lat_grid[:, 0],  z_grid[:, 0]),
        (lon_grid[:, -1], lat_grid[:, -1], z_grid[:, -1])
    ]
    for x_edge, y_edge, z_edge in edges:
        fig3d.add_trace(go.Surface(
            x=np.vstack([x_edge, x_edge]),
            y=np.vstack([y_edge, y_edge]),
            z=np.vstack([z_edge, np.full_like(z_edge, z_base)]),
            colorscale=skirt_color, opacity=1.0, showscale=False,
            lighting=dict(ambient=0.7, diffuse=0.5),
            hoverinfo='skip', showlegend=False
        ))

    fig3d.add_trace(go.Surface(
        x=np.array([[lon_grid[0, 0], lon_grid[0, -1]], [lon_grid[-1, 0], lon_grid[-1, -1]]]),
        y=np.array([[lat_grid[0, 0], lat_grid[0, -1]], [lat_grid[-1, 0], lat_grid[-1, -1]]]),
        z=np.full((2, 2), z_base),
        colorscale=[[0, '#1f2022'], [1, '#1f2022']],
        opacity=1.0, showscale=False, hoverinfo='skip', showlegend=False
    ))

    # 4. Jalur Rute Berwarna di Atas Permukaan Tanah (+16m)
    hover_map = {
        '1. Tanjakan Ekstrem (>15%)': '🔴 Tanjakan Ekstrem (Tembok)',
        '2. Tanjakan Sedang (5-15%)': '🟠 Tanjakan Sedang',
        '3. Datar / Nabung Waktu (-5% s/d 5%)': '🟢 Datar (Nabung Waktu)',
        '4. Turunan Landai (-15% s/d -5%)': '🩵 Turunan Landai',
        '5. Turunan Curam / Quad-Killer (<-15%)': '🔵 Turunan Curam (Jaga Lutut)'
    }
    hover_medan = df['terrain_zone'].map(hover_map)

    for zone, col in color_dict.items():
        mask = df['terrain_zone'] == zone
        sub = df[mask]
        fig3d.add_trace(go.Scatter3d(
            x=sub['lon'], y=sub['lat'], z=sub['ele_smooth'] + 16,
            mode='markers', marker=dict(size=4.5, color=col), name=zone[3:],
            hovertemplate=(
                "<b>KM:</b> %{customdata[0]:.2f}<br>"
                "<b>Medan:</b> %{customdata[2]}<br>"
                "<b>Elevasi:</b> %{customdata[3]:.0f} mdpl<br>"
                "<b>Est. Jam:</b> %{customdata[1]}<extra></extra>"
            ),
            customdata=np.stack((sub['distance_km'], sub['est_time'], hover_medan[mask], sub['ele_smooth']), axis=-1)
        ))

    # 5. Penanda Lokasi Strategis (Start, Finish, Puncak, WS)
    spot_lons = [df['lon'].iloc[0], df['lon'].iloc[-1]]
    spot_lats = [df['lat'].iloc[0], df['lat'].iloc[-1]]
    spot_eles = [df['ele_smooth'].iloc[0] + 60, df['ele_smooth'].iloc[-1] + 60]
    spot_texts = [f"🚩 START ({jam_start})", f"🏁 FINISH ({est_finish})"]
    spot_cols = ['#16a34a', '#dc2626']

    peak_idx = df['ele_smooth'].idxmax()
    spot_lons.append(df.loc[peak_idx, 'lon'])
    spot_lats.append(df.loc[peak_idx, 'lat'])
    spot_eles.append(df.loc[peak_idx, 'ele_smooth'] + 70)
    spot_texts.append(f"⛰️ PUNCAK ({df.loc[peak_idx, 'ele_smooth']:.0f}m | KM {df.loc[peak_idx, 'distance_km']:.1f})")
    spot_cols.append('#d97706')

    for idx, km_ws in enumerate([km for km in ws_list if 0 < km < total_km], start=1):
        r_idx = (df['distance_km'] - km_ws).abs().idxmin()
        spot_lons.append(df.loc[r_idx, 'lon'])
        spot_lats.append(df.loc[r_idx, 'lat'])
        spot_eles.append(df.loc[r_idx, 'ele_smooth'] + 55)
        spot_texts.append(f"💧 WS {idx} (KM {df.loc[r_idx, 'distance_km']:.1f} | {df.loc[r_idx, 'est_time']})")
        spot_cols.append('#0284c7')

    fig3d.add_trace(go.Scatter3d(
        x=spot_lons, y=spot_lats, z=spot_eles,
        mode='markers+text', marker=dict(size=7, color=spot_cols, symbol='diamond'),
        text=spot_texts, textposition='top center', textfont=dict(size=11, color='#1e293b'),
        name='📍 Penanda Lokasi'
    ))

    fig3d.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=540,
        margin=dict(l=0, r=0, b=0, t=20),
        scene=dict(
            bgcolor='rgba(0,0,0,0)',
            xaxis=dict(title='Longitude', showbackground=False, gridcolor='rgba(148,163,184,0.35)', zeroline=False),
            yaxis=dict(title='Latitude', showbackground=False, gridcolor='rgba(148,163,184,0.35)', zeroline=False),
            zaxis=dict(title='Elevasi (mdpl)', showbackground=False, gridcolor='rgba(148,163,184,0.35)', zeroline=False),
            aspectratio=dict(x=1.25, y=1.25, z=0.5),
            camera=dict(eye=dict(x=1.45, y=-1.45, z=1.15))
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    return fig3d