import folium

def build_2d_topo_map(df, ws_list, jam_start, est_finish, color_dict):
    total_km = float(df['distance_km'].max())
    m = folium.Map(location=[df['lat'].mean(), df['lon'].mean()], zoom_start=13, tiles='OpenTopoMap')
    
    for i in range(0, len(df)-1, 3):
        seg = df.iloc[i:i+4]
        if len(seg) > 1:
            folium.PolyLine(
                seg[['lat', 'lon']].values.tolist(),
                color=color_dict[seg['terrain_zone'].iloc[0]],
                weight=5
            ).add_to(m)

    folium.Marker(
        [df['lat'].iloc[0], df['lon'].iloc[0]],
        popup=f"START ({jam_start})",
        icon=folium.Icon(color='green', icon='play')
    ).add_to(m)
    
    folium.Marker(
        [df['lat'].iloc[-1], df['lon'].iloc[-1]],
        popup=f"FINISH ({est_finish})",
        icon=folium.Icon(color='red', icon='flag')
    ).add_to(m)

    for idx, km_ws in enumerate([km for km in ws_list if 0 < km < total_km], start=1):
        r_idx = (df['distance_km'] - km_ws).abs().idxmin()
        folium.Marker(
            [df.loc[r_idx, 'lat'], df.loc[r_idx, 'lon']],
            popup=f"POS / WS {idx} - KM {df.loc[r_idx, 'distance_km']:.1f} (Est. {df.loc[r_idx, 'est_time']})",
            icon=folium.Icon(color='blue', icon='tint')
        ).add_to(m)

    return m