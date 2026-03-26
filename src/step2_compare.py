"""
step2_compare.py
Step 2 – Side-by-side comparison of two GeoDuster sessions.

Runs the core analysis (no plots) for both sessions and produces a
comparison report: sensor status, data quality, configuration diff,
health warnings, and notable differences.

Usage
-----
    python src/step2_compare.py
        Auto-detects data folder and compares the first two sessions found.

    python src/step2_compare.py "data/MyFolder"
        Specify data folder; compares first two sessions found.

    python src/step2_compare.py "data/MyFolder" 6 7
        Compare session 6 vs session 7.

Output
------
    outputs/comparison_NNN_MMM.txt
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geoduster_utils import (
    PROJECT_ROOT, find_sessions, analyse_session,
    ascii_table, COL_DESCRIPTIONS, SENSOR_REFERENCE, WARN_MEANINGS,
)

# ── Carpeta de datos ───────────────────────────────────────────────────────────
# Cambia esta ruta para apuntar a otro dataset.
DATA_DIR = Path(r"D:\Pablo\Repositorios\airborne-survey-explorer\data\2026-03-24 Welzow Ground-Test 006 - 007")
# ──────────────────────────────────────────────────────────────────────────────


def resolve_data_dir(arg):
    p = Path(arg)
    return p if p.is_absolute() else PROJECT_ROOT / p


def auto_find_data_dir():
    data_root = PROJECT_ROOT / "data"
    candidates = [p for p in sorted(data_root.iterdir()) if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No subdirectories found under {data_root}")
    return candidates[0]


def get_sensor_rate(result, sensor_name):
    """Return char rate for a sensor name from a session result dict."""
    for port, sname in result["evt"]["sensor_map"].items():
        if sname == sensor_name:
            return result["evt"]["char_rates"].get(port, 0.0)
    return 0.0


def fmt_stat(result, col, src_key, unit):
    """Return 'mean ± std unit' string or 'NO DATA'."""
    df = result[src_key]
    if col not in df.columns or df[col].isna().all():
        return "NO DATA"
    s = df[col].dropna()
    return f"{s.mean():.3f} ± {s.std():.4f} {unit}".strip()


def main():
    args = sys.argv[1:]

    # ── Determine data directory ───────────────────────────────────────────────
    if args and not args[0].lstrip("-").isdigit():
        data_dir = resolve_data_dir(args.pop(0))
    else:
        data_dir = DATA_DIR

    if not data_dir.exists():
        print(f"ERROR: data folder not found: {data_dir}")
        sys.exit(1)

    # ── Determine the two sessions to compare ─────────────────────────────────
    if len(args) >= 2:
        s_a, s_b = int(args[0]), int(args[1])
    else:
        sessions = find_sessions(data_dir)
        if len(sessions) < 2:
            print(f"ERROR: need at least 2 sessions in {data_dir}, found: {sessions}")
            sys.exit(1)
        s_a, s_b = sessions[0], sessions[1]

    snum_a = str(s_a).zfill(3)
    snum_b = str(s_b).zfill(3)
    out_root = PROJECT_ROOT / "outputs"

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print(f"  STEP 2 – Session Comparison: {snum_a} vs {snum_b}")
    print("=" * 72)
    print(f"\n  Data folder : {data_dir.relative_to(PROJECT_ROOT)}")
    print(f"  Comparing   : session {snum_a}  vs  session {snum_b}")

    # ── Run analysis for both (no plots – step1 handles that) ─────────────────
    print(f"\n  Running analysis for session {snum_a}...")
    r_a = analyse_session(data_dir, s_a, out_root, plots=False)
    print(f"\n  Running analysis for session {snum_b}...")
    r_b = analyse_session(data_dir, s_b, out_root, plots=False)

    # ── Build comparison report ───────────────────────────────────────────────
    comp_lines = []
    def cprint(*args_):
        msg = " ".join(str(a) for a in args_)
        print(msg)
        comp_lines.append(msg)

    cprint()
    cprint("=" * 72)
    cprint(f"  SESSION {snum_a} vs {snum_b}  –  {data_dir.name}")
    cprint("=" * 72)

    # Session timing
    cprint(f"\n── Session timing {'─'*53}")
    cprint(f"  {'Metric':<20} {f'Session {snum_a}':<32} {'Session ' + snum_b}")
    cprint(f"  {'─'*20} {'─'*32} {'─'*25}")
    for metric, key in [("Start",    "session_start"),
                         ("End",      "session_end"),
                         ("Duration", "duration")]:
        cprint(f"  {metric:<20} {str(r_a['evt'][key]):<32} {str(r_b['evt'][key])}")
    for metric, src in [("MAG rows", "mag"), ("GGA rows", "gga"), ("SPC rows", "spc")]:
        cprint(f"  {metric:<20} {str(len(r_a[src])):<32} {len(r_b[src])}")

    # Sensor connection status
    cprint(f"\n── Sensor connection status {'─'*43}")
    all_sensors = sorted(
        set(r_a["evt"]["sensor_map"].values()) | set(r_b["evt"]["sensor_map"].values())
    )
    sensor_rows = []
    changed_sensors = []
    for sensor in all_sensors:
        port  = SENSOR_REFERENCE.get(sensor, {}).get("port", "—")
        rate_a = get_sensor_rate(r_a, sensor)
        rate_b = get_sensor_rate(r_b, sensor)
        st_a   = "CONNECTED" if rate_a > 0 else "DISCONNECTED"
        st_b   = "CONNECTED" if rate_b > 0 else "DISCONNECTED"
        chg    = "CHANGED" if st_a != st_b else "same"
        if st_a != st_b:
            changed_sensors.append(sensor)
        sensor_rows.append((port, sensor, st_a, st_b, chg))
    cprint(ascii_table(
        ["Port", "Sensor", f"Session {snum_a}", f"Session {snum_b}", "Changed?"],
        sensor_rows))

    # Data quality comparison
    cprint(f"\n── Data quality comparison (key channels) {'─'*30}")
    COMPARE_COLS = [
        ("Mag1",  "mag", "nT"),  ("Mag2",  "mag", "nT"),
        ("Mag1C", "mag", "nT"),  ("Mag2C", "mag", "nT"),
        ("Roll",  "mag", "°"),   ("Pitch", "mag", "°"),  ("Yaw",  "mag", "°"),
        ("Ralt",  "mag", "m"),
        ("Xdgps", "gga", "°"),   ("Ydgps", "gga", "°"),
        ("dHdop", "gga", ""),    ("dSNo",  "gga", "sat"),
    ]
    qual_rows = [
        (col,
         COL_DESCRIPTIONS.get(col, "—")[:40],
         fmt_stat(r_a, col, src, unit),
         fmt_stat(r_b, col, src, unit))
        for col, src, unit in COMPARE_COLS
    ]
    cprint(ascii_table(
        ["Column", "Description",
         f"Session {snum_a} (mean ± std)", f"Session {snum_b} (mean ± std)"],
        qual_rows))

    # Configuration diff
    cprint(f"\n── Configuration diff (Cfg XML) {'─'*39}")
    cfg_a, cfg_b = r_a["cfg"], r_b["cfg"]
    all_keys  = set(cfg_a["raw"]) | set(cfg_b["raw"])
    diff_rows = [
        (k, cfg_a["raw"].get(k, "—")[:50], cfg_b["raw"].get(k, "—")[:50])
        for k in sorted(all_keys)
        if cfg_a["raw"].get(k) != cfg_b["raw"].get(k)
    ]
    if diff_rows:
        cprint(ascii_table(
            ["Parameter", f"Session {snum_a}", f"Session {snum_b}"], diff_rows))
    else:
        cprint(f"  Cfg{snum_a} and Cfg{snum_b} are IDENTICAL – no configuration changes.")

    # Health warnings
    cprint(f"\n── Health warning comparison {'─'*43}")
    all_warn  = sorted(set(r_a["warn_counts"]) | set(r_b["warn_counts"]))
    warn_rows = [
        (w,
         str(r_a["warn_counts"].get(w, 0)),
         str(r_b["warn_counts"].get(w, 0)),
         WARN_MEANINGS.get(w, "—"))
        for w in all_warn
    ]
    cprint(ascii_table(
        ["Warning", f"{snum_a} Count", f"{snum_b} Count", "Meaning"],
        warn_rows) if warn_rows else "   None.")

    # Notable differences (data-driven)
    cprint(f"\n── Notable differences {'─'*49}")
    notes = []

    dur_a = r_a["evt"]["duration"]
    dur_b = r_b["evt"]["duration"]
    if dur_a and dur_b and dur_a != dur_b:
        notes.append(f"Duration differs: {snum_a}={dur_a}  vs  {snum_b}={dur_b}")

    if changed_sensors:
        notes.append(f"Sensor status changes: {', '.join(changed_sensors)}")
    else:
        notes.append("Sensor connections identical in both sessions.")

    for col in ["Mag1", "Mag2", "Mag1C", "Mag2C"]:
        df_a = r_a["mag"]
        df_b = r_b["mag"]
        if (col in df_a.columns and col in df_b.columns
                and not df_a[col].isna().all() and not df_b[col].isna().all()):
            diff = abs(df_a[col].dropna().mean() - df_b[col].dropna().mean())
            if diff > 100:
                notes.append(
                    f"{col}: mean difference = {diff:.1f} nT – "
                    f"large discrepancy, check sensor settling")

    for note in notes:
        cprint(f"  • {note}")

    if not notes:
        cprint("  No significant differences detected.")

    # Save comparison report
    comp_path = out_root / f"comparison_{snum_a}_{snum_b}.txt"
    comp_path.parent.mkdir(parents=True, exist_ok=True)
    comp_path.write_text("\n".join(comp_lines), encoding="utf-8")
    print(f"\n  Comparison saved: {comp_path.relative_to(PROJECT_ROOT)}")

    print()
    print("=" * 72)
    print(f"  Step 2 complete: session {snum_a} vs {snum_b}")
    print("=" * 72)


if __name__ == "__main__":
    main()
