import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def _format_duration_hm(total_seconds):
    mins = int(round(total_seconds / 60.0))
    h, m = divmod(mins, 60)
    return f"{h} jam {m:02d} mnt" if h > 0 else f"{m} mnt"

def _evaluate_flexible_cop(cop_input_str, sec_tiba, jam_tiba_hhmm, jam_start_str):
    """
    Mendukung dua format batas COP:
    1) Angka durasi jam dari Start (misal: '5' atau '5.5' -> 5 jam / 5.5 jam)
    2) Format jam dinding HH:MM (misal: '11:30')
    """
    if not cop_input_str or str(cop_input_str).strip() == "":
        return "-", "-"

    raw = str(cop_input_str).strip().lower().replace("jam", "").strip()
    try:
        if ":" in raw:
            # Mode Jam Dinding (HH:MM)
            t_start = datetime.strptime(jam_start_str.strip(), "%H:%M")
            t_tiba = datetime.strptime(jam_tiba_hhmm.strip(), "%H:%M")
            t_cut = datetime.strptime(raw, "%H:%M")
            if t_tiba < t_start: t_tiba += timedelta(days=1)
            if t_cut < t_start: t_cut += timedelta(days=1)
            diff_mins = int((t_cut - t_tiba).total_seconds() // 60)
            label_cop = f"Jam {raw}"
        else:
            # Mode Durasi Jam dari Start (misal 5, 8.5, 16)
            limit_hours = float(raw.replace(",", "."))
            diff_mins = int(round((limit_hours * 60) - (sec_tiba / 60.0)))
            label_cop = f"{limit_hours:g} jam"

        if diff_mins >= 0:
            status = f"🟢 AMAN (Sisa {diff_mins} mnt)"
        else:
            status = f"🔴 LEWAT ({abs(diff_mins)} mnt)"
        return label_cop, status
    except ValueError:
        return "⚠️ Format salah", "⚠️ Gunakan angka jam (5) atau HH:MM"

def generate_ws_logistics(df, ws_list, waktu_berhenti_ws_menit, jam_start_str, cop_config, cot_finish_str, selected_items):
    total_km = float(df['distance_km'].max())
    checkpoints = sorted(list(set([0.0] + [km for km in ws_list if 0 < km < total_km] + [total_km])))
    ws_rows = []
    total_air_all = 0
    total_kal_all = 0

    for idx, km_target in enumerate(checkpoints):
        r_idx = (df['distance_km'] - km_target).abs().idxmin()
        r = df.loc[r_idx]
        sub_from_start = df.iloc[:r_idx+1]

        cum_km = round(float(r['distance_km']), 1)
        cum_gain = int(round(sub_from_start['ele_gain'].sum()))
        cum_loss = int(round(sub_from_start['ele_loss'].sum()))

        if idx == 0:
            ws_rows.append({
                "Pos / COP": "🚩 Start Line",
                "KM": f"{cum_km} km",
                "Elevasi (+/-)": "0m+ / 0m-",
                "Batas COP": "0 detik",
                "Est. Tempuh & Jam": f"0 mnt (Jam {r['est_time']})",
                "Status COP": "🟢 START",
                "Kebutuhan Air": "-",
                "Rencana Logistik": "-"
            })
            continue

        p_idx = (df['distance_km'] - checkpoints[idx-1]).abs().idxmin()
        seg_df = df.iloc[p_idx:r_idx+1]
        seg_moving_mins = seg_df['step_seconds'].sum() / 60.0
        is_finish = (idx == len(checkpoints) - 1)

        if is_finish:
            pos_label = "🏁 Finish Line"
            sec_tiba = float(r['cum_seconds'])
            jam_tiba_hhmm = r['est_time']
            jam_display = f"{_format_duration_hm(sec_tiba)} (Jam {jam_tiba_hhmm})"
            cop_label, status_cp = _evaluate_flexible_cop(cot_finish_str, sec_tiba, jam_tiba_hhmm, jam_start_str)
        else:
            cfg = cop_config.get(idx, {})
            nama_custom = cfg.get("nama", "").strip()
            drop_tag = " 🎒[Drop Bag]" if cfg.get("drop_bag", False) else ""
            pos_label = f"💧 COP {idx}" + (f" - {nama_custom}" if nama_custom else "") + drop_tag

            if waktu_berhenti_ws_menit == 0:
                sec_tiba = float(r['cum_seconds'])
                jam_tiba_hhmm = r['est_time']
                jam_display = f"{_format_duration_hm(sec_tiba)} (Jam {jam_tiba_hhmm})"
            else:
                dt_keluar = datetime.strptime(r['est_time'], "%H:%M")
                dt_masuk = dt_keluar - timedelta(minutes=int(waktu_berhenti_ws_menit))
                jam_tiba_hhmm = dt_masuk.strftime("%H:%M")
                sec_tiba = max(0.0, float(r['cum_seconds']) - (waktu_berhenti_ws_menit * 60))
                jam_display = f"{_format_duration_hm(sec_tiba)} ({jam_tiba_hhmm} ➔ {dt_keluar.strftime('%H:%M')})"

            cop_label, status_cp = _evaluate_flexible_cop(cfg.get("cop", ""), sec_tiba, jam_tiba_hhmm, jam_start_str)

        # Kalkulasi kebutuhan cairan & nutrisi segmen ini
        air_ml = int(round((seg_moving_mins / 60) * 550, -1))
        botol_500 = round(air_ml / 500.0, 1)
        kal_target = int(round((seg_moving_mins / 60) * 200, -1))
        total_air_all += air_ml
        total_kal_all += kal_target
        air_str = f"{air_ml} ml (~{botol_500} botol)"

        if selected_items:
            kal_per_jenis = kal_target / len(selected_items)
            rekom_list = [f"{max(1, round(kal_per_jenis / kcal))}x {name}" for name, kcal in selected_items.items()]
            asupan_str = f"⚡ {', '.join(rekom_list)} (~{kal_target} kkal)"
        else:
            jml_gel = max(1, round(kal_target / 100))
            asupan_str = f"⚡ {jml_gel}x Energy Gel ({kal_target} kkal)"

        ws_rows.append({
            "Pos / COP": pos_label,
            "KM": f"{cum_km} km",
            "Elevasi (+/-)": f"{cum_gain}m+ / {cum_loss}m-",
            "Batas COP": cop_label,
            "Est. Tempuh & Jam": jam_display,
            "Status COP": status_cp,
            "Kebutuhan Air": air_str,
            "Rencana Logistik": asupan_str
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