import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def _evaluate_cutoff(est_time_str, cutoff_str, jam_start_str):
    """Membandingkan jam estimasi tiba dengan batas waktu COP/COT (mendukung lintas tengah malam)."""
    if not cutoff_str or cutoff_str.strip() == "":
        return "-"
    try:
        t_start = datetime.strptime(jam_start_str.strip(), "%H:%M")
        t_est = datetime.strptime(est_time_str.strip(), "%H:%M")
        t_cut = datetime.strptime(cutoff_str.strip(), "%H:%M")
        
        if t_est < t_start:
            t_est += timedelta(days=1)
        if t_cut < t_start:
            t_cut += timedelta(days=1)
            
        diff_mins = int((t_cut - t_est).total_seconds() // 60)
        if diff_mins >= 0:
            return f"🟢 AMAN (+{diff_mins} mnt)"
        else:
            return f"🔴 LEWAT ({abs(diff_mins)} mnt)"
    except ValueError:
        return "⚠️ Format HH:MM"

def generate_ws_logistics(df, ws_list, waktu_berhenti_ws_menit, jam_start_str, cop_dict, cot_str, selected_items):
    total_km = float(df['distance_km'].max())
    checkpoints = sorted(list(set([0.0] + [km for km in ws_list if 0 < km < total_km] + [total_km])))
    ws_rows = []
    total_air_all = 0
    total_kal_all = 0

    for idx, km_target in enumerate(checkpoints):
        r_idx = (df['distance_km'] - km_target).abs().idxmin()
        r = df.loc[r_idx]
        if idx == 0:
            seg_dist, seg_gain, label = 0, 0, "🚩 START"
            jam_tiba_str = r['est_time']
            istirahat_str = "-"
            status_cp = "-"
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
                istirahat_str = "Selesai" if is_finish else "0 mnt"
                jam_cek_cutoff = r['est_time']
            else:
                dt_keluar = datetime.strptime(r['est_time'], "%H:%M")
                dt_masuk = dt_keluar - timedelta(minutes=int(waktu_berhenti_ws_menit))
                jam_tiba_str = f"{dt_masuk.strftime('%H:%M')} (Lanjut {dt_keluar.strftime('%H:%M')})"
                istirahat_str = f"⏸️ {waktu_berhenti_ws_menit} mnt"
                jam_cek_cutoff = dt_masuk.strftime("%H:%M")

            # Cek COP untuk WS atau COT untuk Finish
            if is_finish:
                status_cp = _evaluate_cutoff(jam_cek_cutoff, cot_str, jam_start_str)
            else:
                status_cp = _evaluate_cutoff(jam_cek_cutoff, cop_dict.get(idx, ""), jam_start_str)

            air_ml = int(round((seg_moving_mins / 60) * 550, -1))
            botol_500 = round(air_ml / 500.0, 1)
            kal_target = int(round((seg_moving_mins / 60) * 200, -1))
            
            total_air_all += air_ml
            total_kal_all += kal_target
            air_str = f"{air_ml} ml (~{botol_500} botol)"

            # Distribusi item logistik pilihan pengguna secara proporsional
            if selected_items:
                kal_per_jenis = kal_target / len(selected_items)
                rekom_list = []
                for item_name, item_kcal in selected_items.items():
                    qty = max(1, round(kal_per_jenis / item_kcal))
                    rekom_list.append(f"{qty}x {item_name}")
                asupan_str = f"⚡ {', '.join(rekom_list)} (~{kal_target} kkal)"
            else:
                jml_gel = max(1, round(kal_target / 100))
                asupan_str = f"⚡ {jml_gel}x Energy Gel ({kal_target} kkal)"

        ws_rows.append({
            'Titik Pos': label,
            'KM': round(r['distance_km'], 2),
            'Elevasi': f"{r['ele_smooth']:.0f} mdpl",
            'Segmen': f"{seg_dist:.2f} KM (+{seg_gain:.0f}m)",
            'Jadwal Tiba & Lanjut': jam_tiba_str,
            'Pit Stop': istirahat_str,
            'Status COP / COT': status_cp,
            'Kebutuhan Air': air_str,
            'Rencana Logistik Anda': asupan_str
        })
    return pd.DataFrame(ws_rows), total_air_all, total_kal_all

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