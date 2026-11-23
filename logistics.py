import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def _format_duration_hm(total_seconds):
    mins = int(round(total_seconds / 60.0))
    h, m = divmod(mins, 60)
    return f"{h}j {m:02d}m" if h > 0 else f"{m}m"

def _evaluate_flexible_cop(cop_input_str, sec_tiba, jam_tiba_hhmm, jam_start_str):
    """
    Menyamakan tampilan Batas COP agar selalu memuat Durasi + Jam Dinding,
    sehingga mudah dibandingkan langsung dengan Estimasi Tiba pelari.
    """
    if not cop_input_str or str(cop_input_str).strip() == "":
        return "Tidak ada", "⚪ Tanpa Batas"

    raw = str(cop_input_str).strip().lower().replace("jam", "").strip()
    try:
        t_start = datetime.strptime(jam_start_str.strip(), "%H:%M")
        if ":" in raw:
            t_cut = datetime.strptime(raw, "%H:%M")
            if t_cut < t_start:
                t_cut += timedelta(days=1)
            limit_secs = (t_cut - t_start).total_seconds()
            limit_hours = limit_secs / 3600.0
            jam_cut_str = t_cut.strftime("%H:%M")
        else:
            limit_hours = float(raw.replace(",", "."))
            limit_secs = limit_hours * 3600.0
            t_cut = t_start + timedelta(seconds=limit_secs)
            jam_cut_str = t_cut.strftime("%H:%M")

        diff_mins = int(round((limit_secs - sec_tiba) / 60.0))
        label_cop = f"{limit_hours:g} jam (Jam {jam_cut_str})"

        if diff_mins >= 0:
            status = f"🟢 AMAN (Sisa {diff_mins} mnt)"
        else:
            status = f"🔴 LEWAT ({abs(diff_mins)} mnt)"
        return label_cop, status
    except ValueError:
        return "⚠️ Format salah", "⚠️ Pakai angka (5) / HH:MM"

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
            # Hitung rentang waktu & jarak dari Start menuju COP 1 (atau Finish jika 0 COP)
            next_km = checkpoints[1]
            n_idx = (df['distance_km'] - next_km).abs().idxmin()
            n_row = df.loc[n_idx]
            has_cop = len(checkpoints) > 2

            if has_cop:
                nama_cop1 = cop_config.get(1, {}).get("nama", "").strip()
                tujuan_label = f"COP 1 ({nama_cop1})" if nama_cop1 else "COP 1"
                sec_ke_next = max(0.0, float(n_row['cum_seconds']) - (waktu_berhenti_ws_menit * 60))
                dt_keluar_1 = datetime.strptime(n_row['est_time'], "%H:%M")
                jam_tiba_1 = (dt_keluar_1 - timedelta(minutes=int(waktu_berhenti_ws_menit))).strftime("%H:%M")
                cop1_limit_str, _ = _evaluate_flexible_cop(cop_config.get(1, {}).get("cop", ""), sec_ke_next, jam_tiba_1, jam_start_str)
            else:
                tujuan_label = "Finish Line"
                sec_ke_next = float(n_row['cum_seconds'])
                jam_tiba_1 = n_row['est_time']
                cop1_limit_str, _ = _evaluate_flexible_cop(cot_finish_str, sec_ke_next, jam_tiba_1, jam_start_str)

            durasi_seg1_str = _format_duration_hm(sec_ke_next)
            rentang_start_str = f"Start {r['est_time']} ➔ {jam_tiba_1} ({durasi_seg1_str} ke {tujuan_label})"

            ws_rows.append({
                "Pos / COP": "🚩 Start Line",
                "Batas COP": f"Target {tujuan_label}: {cop1_limit_str}" if cop1_limit_str != "Tidak ada" else "0 detik",
                "Est. Tiba & Status": f"0m (Jam {r['est_time']}) • 🟢 START",
                "Jadwal Lanjut": rentang_start_str,
                "Jarak & Elevasi": f"0.0 ➔ {round(float(n_row['distance_km']), 1)} km",
                "Logistik Segmen": f"Siapkan bekal etape 1 ({durasi_seg1_str})"
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
            jadwal_lanjut = "Selesai"
            cop_label, status_cp = _evaluate_flexible_cop(cot_finish_str, sec_tiba, jam_tiba_hhmm, jam_start_str)
        else:
            cfg = cop_config.get(idx, {})
            nama_custom = cfg.get("nama", "").strip()
            drop_tag = " 🎒[Drop Bag]" if cfg.get("drop_bag", False) else ""
            pos_label = f"💧 COP {idx}" + (f" - {nama_custom}" if nama_custom else "") + drop_tag

            if waktu_berhenti_ws_menit == 0:
                sec_tiba = float(r['cum_seconds'])
                jam_tiba_hhmm = r['est_time']
                jadwal_lanjut = f"Jam {jam_tiba_hhmm} (0 mnt)"
            else:
                dt_keluar = datetime.strptime(r['est_time'], "%H:%M")
                dt_masuk = dt_keluar - timedelta(minutes=int(waktu_berhenti_ws_menit))
                jam_tiba_hhmm = dt_masuk.strftime("%H:%M")
                sec_tiba = max(0.0, float(r['cum_seconds']) - (waktu_berhenti_ws_menit * 60))
                jadwal_lanjut = f"Jam {dt_keluar.strftime('%H:%M')} (Istirahat {waktu_berhenti_ws_menit}m)"

            cop_label, status_cp = _evaluate_flexible_cop(cfg.get("cop", ""), sec_tiba, jam_tiba_hhmm, jam_start_str)

        est_tiba_gabung = f"{_format_duration_hm(sec_tiba)} (Jam {jam_tiba_hhmm}) • {status_cp}"

        air_ml = int(round((seg_moving_mins / 60) * 550, -1))
        botol_500 = round(air_ml / 500.0, 1)
        kal_target = int(round((seg_moving_mins / 60) * 200, -1))
        total_air_all += air_ml
        total_kal_all += kal_target

        if selected_items:
            kal_per_jenis = kal_target / len(selected_items)
            rekom_list = [f"{max(1, round(kal_per_jenis / kcal))}x {name}" for name, kcal in selected_items.items()]
            asupan_str = f"{', '.join(rekom_list)} (~{kal_target} kkal)"
        else:
            jml_gel = max(1, round(kal_target / 100))
            asupan_str = f"{jml_gel}x Energy Gel (~{kal_target} kkal)"

        ws_rows.append({
            "Pos / COP": pos_label,
            "Batas COP": cop_label,
            "Est. Tiba & Status": est_tiba_gabung,
            "Jadwal Lanjut": jadwal_lanjut,
            "Jarak & Elevasi": f"{cum_km} km | {cum_gain}m+ / {cum_loss}m-",
            "Logistik Segmen": f"💧 {air_ml}ml (~{botol_500} btl) | ⚡ {asupan_str}"
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