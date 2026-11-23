import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def generate_ws_logistics(df, ws_list, waktu_berhenti_ws_menit):
    total_km = float(df['distance_km'].max())
    checkpoints = sorted(list(set([0.0] + [km for km in ws_list if 0 < km < total_km] + [total_km])))
    ws_rows = []
    total_gel_all = 0
    total_air_all = 0

    for idx, km_target in enumerate(checkpoints):
        r_idx = (df['distance_km'] - km_target).abs().idxmin()
        r = df.loc[r_idx]
        if idx == 0:
            seg_dist, seg_gain, label = 0, 0, "🚩 START"
            jam_tiba_str = r['est_time']
            istirahat_str = "-"
            air_str, asupan_str = "-", "-"
        else:
            p_idx = (df['distance_km'] - checkpoints[idx-1]).abs().idxmin()
            seg_df = df.iloc[p_idx:r_idx+1]
            seg_dist = r['distance_km'] - df.loc[p_idx, 'distance_km']
            seg_gain = seg_df['ele_gain'].sum()
            seg_moving_mins = seg_df['step_seconds'].sum() / 60.0
            
            is_finish = (idx == len(checkpoints) - 1)
            label = "🏁 FINISH" if is_finish else f"💧 POS / WS {idx}"
            
            if is_finish or waktu_berhenti_ws_menit == 0:
                jam_tiba_str = r['est_time']
                istirahat_str = "Selesai" if is_finish else "0 mnt (Langsung lanjut)"
            else:
                dt_keluar = datetime.strptime(r['est_time'], "%H:%M")
                dt_masuk = dt_keluar - timedelta(minutes=int(waktu_berhenti_ws_menit))
                jam_tiba_str = f"{dt_masuk.strftime('%H:%M')} (Lanjut {dt_keluar.strftime('%H:%M')})"
                istirahat_str = f"⏸️ {waktu_berhenti_ws_menit} menit"

            air_ml = int(round((seg_moving_mins / 60) * 550, -1))
            botol_500 = round(air_ml / 500.0, 1)
            kal = int(round((seg_moving_mins / 60) * 200, -1))
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
            'Jadwal Tiba & Lanjut': jam_tiba_str,
            'Durasi Pit Stop': istirahat_str,
            'Kebutuhan Air': air_str,
            'Rekomendasi Asupan Energi': asupan_str
        })
    return pd.DataFrame(ws_rows), total_air_all, total_gel_all

def generate_per_km_strategy(df):
    df_calc = df.copy()
    total_km = float(df_calc['distance_km'].max())
    df_calc['km_ke'] = np.floor(df_calc['distance_km']).astype(int) + 1
    df_calc.loc[df_calc['distance_km'] == total_km, 'km_ke'] = int(np.ceil(total_km))
    
    km_splits = []
    for km_num, group in df_calc.groupby('km_ke'):
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
    return pd.DataFrame(km_splits)