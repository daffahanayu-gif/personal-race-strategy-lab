import streamlit as st
from streamlit_folium import st_folium
from engine import parse_gpx_data, run_strategy_simulation
from terrain_3d import build_3d_terrain_figure
from map_2d import build_2d_topo_map
from logistics import generate_ws_logistics, generate_per_km_strategy

st.set_page_config(page_title="Personal Race Strategy Lab", page_icon="🏔️", layout="wide")

st.markdown("""
<style>
    @media (max-width: 768px) {
        [data-testid="stMetricValue"] { font-size: 1.4rem !important; }
        [data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
    }
</style>
""", unsafe_allow_html=True)

st.title("🏔️ Personal Race Strategy Lab")
st.caption("Analisis rute GPX, pemodelan kontur medan 3D, simulasi pacing berbasis gradien, dan perencanaan logistik otomatis.")

# --- SIDEBAR PENGATURAN ---
with st.sidebar:
    st.header("⚙️ Pengaturan Rute & Target")
    uploaded_file = st.file_uploader("1. Unggah Berkas GPX (.gpx)", type=["gpx"], key="sidebar_uploader")
    st.divider()
    jam_start = st.text_input("2. Waktu Mulai / Start (HH:MM)", value="06:00")
    target_durasi = st.number_input("3. Target Durasi (Jam)", min_value=0.5, max_value=48.0, value=4.15, step=0.25)
    mode_strategi = st.selectbox(
        "4. Strategi Pacing",
        ["Normal (Stabil)", "Konservatif (Simpan Tenaga di Awal)", "Agresif (Cepat di Awal)"]
    )
    waktu_berhenti_ws = st.number_input(
    "5. Estimasi Berhenti per WS (Menit)",
    min_value=0, max_value=60, value=3, step=1,
    help="Waktu pit-stop di setiap pos hidrasi (isi ulang botol, makan, peregangan). Otomatis memengaruhi target pace lari."
)

# --- TAMPILAN AWAL (EMPTY STATE PROFESIONAL) ---
if uploaded_file is None:
    st.markdown("### Mulai Analisis Strategi Rute Anda")
    st.markdown(
        "Unggah berkas lintasan **`.gpx`** untuk menghasilkan simulasi *pacing* berbasis gradien, "
        "visualisasi kontur topografi 3D, serta perencanaan logistik hidrasi dan nutrisi secara otomatis."
    )
    uploaded_main = st.file_uploader("Pilih berkas GPX dari perangkat Anda", type=["gpx"], key="main_uploader")
    st.caption(
        "💡 **Navigasi Parameter:** Gunakan panel **Pengaturan Rute & Target** di sisi kiri layar "
        "(atau ketuk ikon menu **`>>`** di pojok kiri atas pada layar seluler) untuk menyesuaikan "
        "waktu mulai, target durasi, strategi *pacing*, serta titik pos logistik."
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
    st.caption("Geser (drag) untuk memutar sudut pandang dan cubit/gulir untuk memperbesar kontur elevasi.")
    fig3d = build_3d_terrain_figure(df, ws_list, jam_start, est_finish, color_dict)
    st.plotly_chart(fig3d, use_container_width=True)

with tab_2d:
    st.subheader("Peta Topografi 2D & Titik Pos")
    topo_map = build_2d_topo_map(df, ws_list, jam_start, est_finish, color_dict)
    st_folium(topo_map, use_container_width=True, height=540, returned_objects=[])

with tab_ws:
    st.subheader("Jadwal Kedatangan & Perencanaan Logistik per Pos")
    st.caption("Estimasi konversi: 1 Energy Gel ≈ 100 kkal | 1 Pisang/Kurma ≈ 90–100 kkal | 1 Soft Flask = 500 ml.")
    df_ws, total_air, total_gel = generate_ws_logistics(df, ws_list, waktu_berhenti_ws)
    st.dataframe(df_ws, use_container_width=True, hide_index=True)
    st.success(
        f"🎒 **Ringkasan Logistik ({target_durasi} Jam):** Siapkan total sekitar **{total_air} ml cairan** "
        f"dan **{total_gel} porsi energi** (Energy Gel, pisang, atau kurma) yang didistribusikan sesuai tabel di atas."
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