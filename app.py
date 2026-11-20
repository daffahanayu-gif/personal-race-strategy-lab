import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
from engine import parse_gpx_data, run_strategy_simulation, fetch_terrain_surface

st.set_page_config(page_title="Personal Race Strategy Lab", page_icon="🏔️", layout="wide")

st.title("🏔️ Personal Race Strategy Lab")
st.caption("Analisis rute GPX, simulasi effort-adjusted pacing, pemetaan 2D/3D, dan logistik lomba otomatis.")

# --- SIDEBAR INPUT ---
with st.sidebar:
    st.header("⚙️ Pengaturan Rute & Target")
    uploaded_file = st.file_uploader("1. Unggah File GPX (.gpx)", type=["gpx"])
    
    st.divider()
    jam_start = st.text_input("2. Jam Start (HH:MM)", value="06:00")
    target_durasi = st.number_input("3. Target Durasi (Jam)", min_value=0.5, max_value=48.0, value=4.15, step=0.25)
    mode_strategi = st.selectbox(
        "4. Strategi Pacing",
        ["Normal (Stabil)", "Konservatif (Simpan Tenaga di Awal)", "Agresif (Cepat di Awal)"]
    )
    ws_input = st.text_input("5. Lokasi Pos / WS (KM)", value="", placeholder="Kosongkan = Otomatis (misal: 8, 16.5)")

# --- KONTEN UTAMA ---
if uploaded_file is None:
    st.info("👈 Silakan unggah file **.gpx** di panel sebelah kiri untuk memulai simulasi strategi rute.")
else:
    @st.cache_data
    def load_cached_gpx(file_bytes):
        return parse_gpx_data(file_bytes)

    df_raw = load_cached_gpx(uploaded_file.getvalue())
    df, ws_list, ws_mode = run_strategy_simulation(df_raw, jam_start, target_durasi, ws_input, mode_strategi)
    
    total_km = float(df['distance_km'].max())
    total_gain = float(df['ele_gain'].sum())
    max_ele = float(df['ele_smooth'].max())
    est_finish = df['est_time'].iloc[-1]

    # Kartu Metrik Ringkasan
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Jarak", f"{total_km:.2f} KM")
    c2.metric("Total Tanjakan (EG)", f"+{total_gain:.0f} m")
    c3.metric("Puncak Tertinggi", f"{max_ele:.0f} mdpl")
    c4.metric("Estimasi Finis", f"Jam {est_finish}", delta=ws_mode, delta_color="off")

    st.divider()

    # Navigasi Tab (Dipisah agar lega dan tidak menumpuk!)
    tab_3d, tab_2d, tab_ws, tab_km = st.tabs([
        "⛰️ Model Medan 3D",
        "🗺️ Peta Topografi 2D",
        "💧 Jadwal Pos & Logistik Makanan",
        "📊 Strategi Per 1 KM"
    ])

    color_dict = {
        '1. Tanjakan Ekstrem (>15%)': '#ff2a2a',
        '2. Tanjakan Sedang (5-15%)': '#ff9f1a',
        '3. Datar / Nabung Waktu (-5% s/d 5%)': '#2ed573',
        '4. Turunan Landai (-15% s/d -5%)': '#70a1ff',
        '5. Turunan Curam / Quad-Killer (<-15%)': '#5352ed'
    }

    # --- TAB 1: MODEL MEDAN 3D (MAKET GUNUNG SOLID TANPA LATAR HITAM) ---
    with tab_3d:
        st.subheader("Visualisasi Maket Gunung & Lintasan 3D (Realistic Terrain)")
        st.caption("Putar (drag) atau zoom model maket 3D untuk melihat punggungan bukit, lembah, dan elevasi lintasan secara utuh.")

        @st.cache_data(show_spinner="Membentuk maket topografi gunung 3D...")
        def get_cached_terrain_v2(lat_min, lat_max, lon_min, lon_max):
            return fetch_terrain_surface(df, grid_size=28)

        lon_grid, lat_grid, z_grid = get_cached_terrain_v2(
            round(df['lat'].min(), 4), round(df['lat'].max(), 4),
            round(df['lon'].min(), 4), round(df['lon'].max(), 4)
        )

        hover_map = {
            '1. Tanjakan Ekstrem (>15%)': '🔴 Tanjakan Ekstrem (Tembok)',
            '2. Tanjakan Sedang (5-15%)': '🟠 Tanjakan Sedang',
            '3. Datar / Nabung Waktu (-5% s/d 5%)': '🟢 Datar (Nabung Waktu)',
            '4. Turunan Landai (-15% s/d -5%)': '🩵 Turunan Landai',
            '5. Turunan Curam / Quad-Killer (<-15%)': '🔵 Turunan Curam (Jaga Lutut)'
        }
        df['hover_medan'] = df['terrain_zone'].map(hover_map)
        fig3d = go.Figure()

        # 1. Permukaan Tanah Padat (Solid) dengan Efek Bayangan Tebing (Hillshade Lighting)
        if z_grid is not None:
            # Palet warna alami mirip maket topografi realistis (lembah hijau zaitun -> lereng tanah -> puncak batu terang)
            realistic_earth_scale = [
                [0.0, '#4a6b48'],
                [0.25, '#7c8c58'],
                [0.50, '#b5a273'],
                [0.75, '#967c54'],
                [1.0, '#d6cbb5']
            ]
            fig3d.add_trace(go.Surface(
                x=lon_grid,
                y=lat_grid,
                z=z_grid,
                colorscale=realistic_earth_scale,
                opacity=1.0,             # Padat 100% tidak tembus pandang
                showscale=False,
                lighting=dict(
                    ambient=0.45,        # Cahaya dasar
                    diffuse=0.85,        # Bayangan lereng & tebing agar tekstur gunung muncul tajam
                    specular=0.15,
                    roughness=0.85,
                    fresnel=0.1
                ),
                lightposition=dict(x=100, y=200, z=500),
                contours=dict(
                    z=dict(show=True, color='rgba(60, 45, 30, 0.28)', width=1)
                ),
                hoverinfo='skip',
                name='Kontur Bukit 3D'
            ))

        # 2. Jalur Rute Mengambang Tipis (+18m) di Atas Permukaan Padat Agar Tidak Tenggelam
        for zone, col in color_dict.items():
            sub = df[df['terrain_zone'] == zone]
            fig3d.add_trace(go.Scatter3d(
                x=sub['lon'], y=sub['lat'], z=sub['ele_smooth'] + 18,
                mode='markers', marker=dict(size=4.8, color=col), name=zone[3:],
                hovertemplate=(
                    "<b>KM:</b> %{customdata[0]:.2f}<br>"
                    "<b>Medan:</b> %{customdata[2]}<br>"
                    "<b>Elevasi:</b> %{customdata[3]:.0f} mdpl<br>"
                    "<b>Est. Jam:</b> %{customdata[1]}<extra></extra>"
                ),
                customdata=np.stack((sub['distance_km'], sub['est_time'], sub['hover_medan'], sub['ele_smooth']), axis=-1)
            ))

        # 3. Pin Penanda Lokasi (Start, Finish, Puncak, WS)
        spot_lons = [df['lon'].iloc[0], df['lon'].iloc[-1]]
        spot_lats = [df['lat'].iloc[0], df['lat'].iloc[-1]]
        spot_eles = [df['ele_smooth'].iloc[0] + 65, df['ele_smooth'].iloc[-1] + 65]
        spot_texts = [f"🚩 START ({jam_start})", f"🏁 FINISH ({est_finish})"]
        spot_cols = ['#16a34a', '#dc2626']

        peak_idx = df['ele_smooth'].idxmax()
        spot_lons.append(df.loc[peak_idx, 'lon'])
        spot_lats.append(df.loc[peak_idx, 'lat'])
        spot_eles.append(df.loc[peak_idx, 'ele_smooth'] + 75)
        spot_texts.append(f"⛰️ PUNCAK ({df.loc[peak_idx, 'ele_smooth']:.0f}m | KM {df.loc[peak_idx, 'distance_km']:.1f})")
        spot_cols.append('#d97706')

        for idx, km_ws in enumerate([km for km in ws_list if 0 < km < total_km], start=1):
            r_idx = (df['distance_km'] - km_ws).abs().idxmin()
            spot_lons.append(df.loc[r_idx, 'lon'])
            spot_lats.append(df.loc[r_idx, 'lat'])
            spot_eles.append(df.loc[r_idx, 'ele_smooth'] + 60)
            spot_texts.append(f"💧 WS {idx} (KM {df.loc[r_idx, 'distance_km']:.1f} | {df.loc[r_idx, 'est_time']})")
            spot_cols.append('#0284c7')

        fig3d.add_trace(go.Scatter3d(
            x=spot_lons, y=spot_lats, z=spot_eles,
            mode='markers+text', marker=dict(size=7, color=spot_cols, symbol='diamond'),
            text=spot_texts, textposition='top center',
            textfont=dict(size=11, color='#1e293b'),
            name='📍 Penanda Lokasi'
        ))

        fig3d.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=660,
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
        st.plotly_chart(fig3d, use_container_width=True)

    # --- TAB 2: PETA TOPOGRAFI 2D (FULL WIDTH LEGA) ---
    with tab_2d:
        st.subheader("Peta Topografi 2D & Titik Pos")
        m = folium.Map(location=[df['lat'].mean(), df['lon'].mean()], zoom_start=13, tiles='OpenTopoMap')
        for i in range(0, len(df)-1, 3):
            seg = df.iloc[i:i+4]
            if len(seg) > 1:
                folium.PolyLine(seg[['lat', 'lon']].values.tolist(), color=color_dict[seg['terrain_zone'].iloc[0]], weight=5).add_to(m)
        
        folium.Marker([df['lat'].iloc[0], df['lon'].iloc[0]], popup=f"START ({jam_start})", icon=folium.Icon(color='green', icon='play')).add_to(m)
        folium.Marker([df['lat'].iloc[-1], df['lon'].iloc[-1]], popup=f"FINISH ({est_finish})", icon=folium.Icon(color='red', icon='flag')).add_to(m)
        for idx, km_ws in enumerate([km for km in ws_list if 0 < km < total_km], start=1):
            r_idx = (df['distance_km'] - km_ws).abs().idxmin()
            folium.Marker(
                [df.loc[r_idx, 'lat'], df.loc[r_idx, 'lon']],
                popup=f"POS / WS {idx} - KM {df.loc[r_idx, 'distance_km']:.1f} (Est. {df.loc[r_idx, 'est_time']})",
                icon=folium.Icon(color='blue', icon='tint')
            ).add_to(m)
        st_folium(m, use_container_width=True, height=580, returned_objects=[])

    # --- TAB 3: JADWAL POS & KONVERSI LOGISTIK (GEL / PISANG / BOTOL) ---
    with tab_ws:
        st.subheader("Jadwal Kedatangan & Panduan Logistik Praktis per Pos")
        st.caption("Konversi otomatis: 1 Energy Gel ≈ 100 kkal | 1 Pisang/Kurma ≈ 90–100 kkal | 1 Soft Flask = 500 ml.")
        
        checkpoints = sorted(list(set([0.0] + [km for km in ws_list if 0 < km < total_km] + [total_km])))
        ws_rows = []
        total_gel_all = 0
        total_air_all = 0

        for idx, km_target in enumerate(checkpoints):
            r_idx = (df['distance_km'] - km_target).abs().idxmin()
            r = df.loc[r_idx]
            if idx == 0:
                seg_dist, seg_gain, seg_mins, label = 0, 0, 0, "🚩 START"
                air_str, asupan_str = "-", "-"
            else:
                p_idx = (df['distance_km'] - checkpoints[idx-1]).abs().idxmin()
                seg_df = df.iloc[p_idx:r_idx+1]
                seg_dist = r['distance_km'] - df.loc[p_idx, 'distance_km']
                seg_gain = seg_df['ele_gain'].sum()
                seg_mins = (r['cum_seconds'] - df.loc[p_idx, 'cum_seconds']) / 60
                label = "🏁 FINISH" if idx == len(checkpoints)-1 else f"💧 POS / WS {idx}"
                
                air_ml = int(round((seg_mins / 60) * 550, -1))
                botol_500 = round(air_ml / 500.0, 1)
                kal = int(round((seg_mins / 60) * 200, -1))
                jml_gel = max(1, round(kal / 100))
                
                total_air_all += air_ml
                total_gel_all += jml_gel

                air_str = f"{air_ml} ml (~{botol_500} botol 500ml)"
                asupan_str = f"⚡ {jml_gel} Energy Gel / {jml_gel} Pisang ({kal} kkal)"

            ws_rows.append({
                'Titik Pos': label,
                'KM': round(r['distance_km'], 2),
                'Elevasi': f"{r['ele_smooth']:.0f} mdpl",
                'Jarak Segmen': f"{seg_dist:.2f} KM",
                'Tanjakan': f"+{seg_gain:.0f} m",
                'Target Jam Tiba': r['est_time'],
                'Kebutuhan Air': air_str,
                'Rekomendasi Asupan Energi': asupan_str
            })
        
        df_ws = pd.DataFrame(ws_rows)
        st.dataframe(df_ws, use_container_width=True, hide_index=True)

        # Ringkasan Total Bawaan di Bawah Tabel
        st.success(
            f"🎒 **Total Bekal Sepanjang Lomba ({target_durasi} Jam):** Siapkan total sekitar **{total_air_all} ml air** "
            f"dan **{total_gel_all} bungkus Energy Gel** (atau kombinasi pisang/kurma/roti manis) yang dibagi rata per pos di atas."
        )

    # --- TAB 4: STRATEGI PER 1 KM ---
    with tab_km:
        st.subheader("Rincian Target Pace & Karakter Medan Per 1 Kilometer")
        df['km_ke'] = np.floor(df['distance_km']).astype(int) + 1
        df.loc[df['distance_km'] == total_km, 'km_ke'] = int(np.ceil(total_km))
        km_splits = []
        for km_num, group in df.groupby('km_ke'):
            dist_s = group['dist_step_m'].sum() / 1000.0
            if dist_s < 0.05: continue
            gain_s, loss_s = group['ele_gain'].sum(), group['ele_loss'].sum()
            pace_dec = (group['step_seconds'].sum() / 60.0) / dist_s
            p_m, p_s = int(pace_dec), int((pace_dec - int(pace_dec)) * 60)
            status = (
                "🔴 Tanjakan Berat (Power Hike)" if gain_s > 80 else
                ("🟠 Menanjak (Jaga Ritme)" if gain_s > 35 else
                ("🔵 Turunan Tajam (Jaga Lutut)" if loss_s > 80 else
                "🟢 Datar / Mengalir (Nabung Waktu)"))
            )
            km_splits.append({
                'KM': f"KM {km_num}",
                'Elevasi Akhir': f"{group['ele_smooth'].iloc[-1]:.0f} mdpl",
                'Naik': f"+{gain_s:.0f} m",
                'Turun': f"-{loss_s:.0f} m",
                'Target Pace': f"{p_m}:{p_s:02d} /km",
                'Est. Jam Tiba': group['est_time'].iloc[-1],
                'Instruksi Medan': status
            })
        df_km = pd.DataFrame(km_splits)
        st.dataframe(df_km, use_container_width=True, hide_index=True)
        st.download_button("📥 Unduh Tabel Strategi Per 1 KM (CSV)", df_km.to_csv(index=False).encode('utf-8'), "strategi_per_km.csv", "text/csv")