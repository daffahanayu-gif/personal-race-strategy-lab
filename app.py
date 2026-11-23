import streamlit as st
from streamlit_folium import st_folium
from engine import parse_gpx_data, run_strategy_simulation
from terrain_3d import build_3d_terrain_figure
from map_2d import build_2d_topo_map
from logistics import generate_ws_logistics, generate_per_km_strategy

st.set_page_config(page_title="Personal Race Strategy Lab", page_icon="🏔️", layout="wide")

def parse_duration_to_hours(durasi_str):
    try:
        parts = [int(p.strip()) for p in durasi_str.split(":")]
        if len(parts) == 3: h, m, s = parts
        elif len(parts) == 2: h, m, s = parts[0], parts[1], 0
        else: return None
        if h < 0 or not (0 <= m < 60) or not (0 <= s < 60): return None
        total_hours = h + (m / 60.0) + (s / 3600.0)
        return total_hours if total_hours > 0 else None
    except ValueError:
        return None

st.markdown("""
<style>
    @media (max-width: 768px) {
        [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
    }
</style>
""", unsafe_allow_html=True)

st.title("🏔️ Personal Race Strategy Lab")
st.caption("Analisis rute GPX, pemodelan kontur medan 3D, simulasi pacing berbasis gradien, evaluasi COP/COT, dan manajemen logistik.")

# Inisialisasi daftar logistik kustom di session_state
if "custom_logistics_catalog" not in st.session_state:
    st.session_state.custom_logistics_catalog = {
        "Energy Gel (100 kkal)": 100,
        "Pisang (95 kkal)": 95,
        "Kurma 3 Butir (70 kkal)": 70,
        "Energy Bar (180 kkal)": 180,
        "Minuman Isotonik 500ml (120 kkal)": 120,
        "Roti / Onigiri (160 kkal)": 160
    }

# --- SIDEBAR PENGATURAN ---
with st.sidebar:
    st.header("⚙️ Pengaturan Rute & Target")
    uploaded_file = st.file_uploader("1. Unggah Berkas GPX (.gpx)", type=["gpx"], key="sidebar_uploader")
    st.divider()
    jam_start = st.text_input("2. Waktu Mulai / Start (HH:MM)", value="06:00")
    target_durasi_str = st.text_input("3. Target Durasi (HH:MM:SS)", value="04:15:00")
    target_durasi = parse_duration_to_hours(target_durasi_str)
    if target_durasi is None:
        st.error("⚠️ Format durasi tidak valid. Gunakan format **HH:MM:SS** (contoh: `04:15:00`).")
        st.stop()

    mode_strategi = st.selectbox(
        "4. Strategi Pacing",
        ["Normal (Stabil)", "Konservatif (Simpan Tenaga di Awal)", "Agresif (Cepat di Awal)"]
    )
    waktu_berhenti_ws = st.number_input(
        "5. Estimasi Berhenti per WS (Menit)",
        min_value=0, max_value=60, value=3, step=1
    )
    cot_input = st.text_input(
        "6. Cut-Off Time / COT Finis (HH:MM)",
        value="",
        placeholder="Opsional (misal: 12:00)"
    )

# --- TAMPILAN AWAL ---
if uploaded_file is None:
    st.markdown("### Mulai Analisis Strategi Rute Anda")
    st.markdown(
        "Unggah berkas lintasan **`.gpx`** untuk menghasilkan simulasi *pacing* berbasis gradien, "
        "visualisasi kontur topografi 3D, evaluasi batas waktu COP/COT, serta perencanaan logistik otomatis."
    )
    uploaded_main = st.file_uploader("Pilih berkas GPX dari perangkat Anda", type=["gpx"], key="main_uploader")
    st.caption(
        "💡 **Navigasi Parameter:** Gunakan panel **Pengaturan Rute & Target** di sisi kiri layar "
        "(atau ketuk ikon menu **`>>`** di pojok kiri atas pada layar seluler) untuk menyesuaikan "
        "waktu mulai, target durasi, strategi *pacing*, lama pit-stop WS, serta batas waktu COT."
    )
    if uploaded_main is not None:
        uploaded_file = uploaded_main
    else:
        st.stop()

# --- EKSEKUSI ANALISIS ---
@st.cache_data
def load_cached_gpx(file_bytes):
    return parse_gpx_data(file_bytes)

df_raw = load_cached_gpx(uploaded_file.getvalue())
df, ws_list, ws_mode = run_strategy_simulation(df_raw, jam_start, target_durasi, waktu_berhenti_ws, mode_strategi)

total_km = float(df['distance_km'].max())
total_gain = float(df['ele_gain'].sum())
max_ele = float(df['ele_smooth'].max())
est_finish = df['est_time'].iloc[-1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Jarak", f"{total_km:.2f} KM")
c2.metric("Total Tanjakan (EG)", f"+{total_gain:.0f} m")
c3.metric("Puncak Tertinggi", f"{max_ele:.0f} mdpl")
c4.metric("Estimasi Finis", f"Jam {est_finish}", delta=ws_mode, delta_color="off")

st.divider()

color_dict = {
    '1. Tanjakan Ekstrem (>15%)': '#ff2a2a',
    '2. Tanjakan Sedang (5-15%)': '#ff9f1a',
    '3. Datar / Nabung Waktu (-5% s/d 5%)': '#2ed573',
    '4. Turunan Landai (-15% s/d -5%)': '#70a1ff',
    '5. Turunan Curam / Quad-Killer (<-15%)': '#5352ed'
}

tab_3d, tab_2d, tab_ws, tab_km = st.tabs([
    "⛰️ Model Medan 3D",
    "🗺️ Peta Topografi 2D",
    "💧 Jadwal Pos & Logistik",
    "📊 Strategi Per 1 KM"
])

with tab_3d:
    st.subheader("Visualisasi Maket Gunung & Lintasan 3D")
    st.caption("📱 **Kontrol HP:** Geser **1 jari** untuk memutar maket, **ketuk titik** untuk detail elevasi, dan gunakan **penggeser Zoom** di bawah untuk memperbesar kontur tanpa memperbesar layar browser.")
    
    zoom_3d = st.slider("🔍 Tingkat Zoom Maket 3D", min_value=0.7, max_value=2.5, value=1.0, step=0.1)
    fig3d = build_3d_terrain_figure(df, ws_list, jam_start, est_finish, color_dict, zoom_level=zoom_3d)
    st.plotly_chart(
        fig3d,
        use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": False}
    )

with tab_2d:
    st.subheader("Peta Topografi 2D & Titik Pos")
    topo_map = build_2d_topo_map(df, ws_list, jam_start, est_finish, color_dict)
    st_folium(topo_map, use_container_width=True, height=540, returned_objects=[])

with tab_ws:
    st.subheader("Jadwal Pos, Evaluasi COP/COT & Perencanaan Logistik")
    
    # Panel Kustomisasi COP per Pos & Logistik Pengguna
    with st.expander("🛠️ Atur Cut-Off Point (COP) Pos & Pilih Logistik Anda", expanded=True):
        col_cop, col_log = st.columns([1, 1.3])
        
        with col_cop:
            st.markdown("**1. Batas Waktu per Pos / COP (Opsional)**")
            cop_dict = {}
            if ws_list:
                for idx_ws, km_w in enumerate(ws_list, start=1):
                    cop_dict[idx_ws] = st.text_input(
                        f"COP WS {idx_ws} (KM {km_w})",
                        value="",
                        placeholder="Format HH:MM (misal: 08:30)",
                        key=f"cop_ws_{idx_ws}"
                    )
            else:
                st.caption("Rute pendek (tidak ada pos antara).")

        with col_log:
            st.markdown("**2. Pilih Jenis Logistik yang Dibawa**")
            pilihan_nama = st.multiselect(
                "Pilih dari daftar logistik:",
                options=list(st.session_state.custom_logistics_catalog.keys()),
                default=["Energy Gel (100 kkal)", "Pisang (95 kkal)"]
            )
            
            # Tambah item logistik baru ke katalog sistem
            c_new1, c_new2, c_new3 = st.columns([2, 1.2, 1])
            new_item_name = c_new1.text_input("Tambah item baru", placeholder="Misal: Dodol / Gel Caff", label_visibility="collapsed")
            new_item_kcal = c_new2.number_input("Kalori (kkal)", min_value=10, max_value=1000, value=110, step=10, label_visibility="collapsed")
            if c_new3.button("➕ Tambah", use_container_width=True):
                if new_item_name.strip():
                    label_baru = f"{new_item_name.strip()} ({new_item_kcal} kkal)"
                    st.session_state.custom_logistics_catalog[label_baru] = new_item_kcal
                    st.rerun()

    selected_items_dict = {k: st.session_state.custom_logistics_catalog[k] for k in pilihan_nama}

    df_ws, total_air, total_kal = generate_ws_logistics(
        df, ws_list, waktu_berhenti_ws, jam_start, cop_dict, cot_input, selected_items_dict
    )
    st.dataframe(df_ws, use_container_width=True, hide_index=True)
    st.success(
        f"🎒 **Ringkasan Logistik (Target {target_durasi_str}):** Total kebutuhan cairan sekitar **{total_air} ml** "
        f"dan total kebutuhan energi sekitar **{total_kal} kkal** yang dibagi proporsional ke item pilihan Anda."
    )

with tab_km:
    st.subheader("Rincian Target Pace & Karakter Medan Per 1 Kilometer")
    df_km = generate_per_km_strategy(df)
    st.dataframe(df_km, use_container_width=True, hide_index=True)
    st.download_button(
        "📥 Unduh Tabel Strategi Per 1 KM (CSV)",
        df_km.to_csv(index=False).encode('utf-8'),
        "strategi_per_km.csv",
        "text/csv"
    )