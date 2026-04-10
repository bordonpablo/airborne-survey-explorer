"""
step1_status.py
Step 1 – Sensor health and initial data-quality check for GeoDuster sessions.

Scans the data folder for available sessions (EVT*.txt files), runs a full
status report for each (EVT log, MAG/GGA/SPC quality, stability analysis,
cross-check, plots), and saves a text report per session.

Usage
-----
    python src/step1_status.py
        Auto-detects the first subfolder under data/ and all sessions in it.

    python src/step1_status.py "data/MyFolder"
        Specify data folder; sessions auto-detected.

    python src/step1_status.py "data/MyFolder" 6 7
        Specify data folder and exact session numbers.

Outputs
-------
    outputs/session_NNN/report_NNN.txt
    outputs/session_NNN/plot_01_mag_raw.png
    outputs/session_NNN/plot_02_mag_compensated.png
    ... (8 plots total per session)
"""

import sys
from pathlib import Path

# Allow running from project root or src/
sys.path.insert(0, str(Path(__file__).resolve().parent))
from geoduster_utils import (
    PROJECT_ROOT, find_sessions, analyse_session,
    ascii_table, SENSOR_REFERENCE, SENSOR_MAG_COLS, STABILITY_THRESHOLDS,
)

# ── Carpeta de datos ───────────────────────────────────────────────────────────
# Cambia esta ruta para apuntar a otro dataset.
DATA_DIR = Path(r"D:\Pablo\Repositorios\airborne-survey-explorer\data\2026-03-24 Welzow Ground-Test 006 - 007")
# ──────────────────────────────────────────────────────────────────────────────


def resolve_data_dir(arg):
    """Turn a user-supplied path (absolute or relative to project root) into a Path."""
    p = Path(arg)
    return p if p.is_absolute() else PROJECT_ROOT / p


def auto_find_data_dir():
    """Return the first subfolder found under PROJECT_ROOT/data/."""
    data_root = PROJECT_ROOT / "data"
    candidates = [p for p in sorted(data_root.iterdir()) if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No subdirectories found under {data_root}")
    return candidates[0]


def _sensor_status(result, sensor):
    """Return terminal status string for one sensor from a session result."""
    port = SENSOR_REFERENCE[sensor]["port"]
    rate = result["evt"]["char_rates"].get(port, 0.0)
    if rate == 0.0:
        return "DISCONNECTED"
    mag, spc = result["mag"], result["spc"]
    cols = SENSOR_MAG_COLS.get(sensor, [])
    has  = any(c in mag.columns and not mag[c].isna().all() for c in cols)
    if not has and sensor == "GDSpec":
        has = any(c in spc.columns and not spc[c].isna().all()
                  for c in ["Sk", "Su", "Sth"])
    if not cols and sensor != "GDSpec":
        has = True
    return "OK  connected" if has else "NO DATA"


def _print_comparison(results, out_root):
    """Print compact side-by-side comparison for 2+ sessions."""
    snums = [r["session"] for r in results]

    print()
    print("=" * 72)
    print(f"  SESSION COMPARISON: {' vs '.join(snums)}")
    print("=" * 72)

    # Sensor connection status side by side
    print(f"\n-- Sensor connection status {'-'*43}")
    hdr = ["Sensor", "Full Name"] + [f"Session {s}" for s in snums]
    rows = [
        (sensor, SENSOR_REFERENCE[sensor]["full_name"],
         *[_sensor_status(r, sensor) for r in results])
        for sensor in SENSOR_REFERENCE
    ]
    print(ascii_table(hdr, rows))

    # Key variable means side by side
    print(f"\n-- Key variable means {'-'*49}")
    COMPARE_VARS = [
        ("Mag1",  "mag"), ("Mag2",  "mag"), ("Mag1C", "mag"), ("Mag2C", "mag"),
        ("Roll",  "mag"), ("Pitch", "mag"), ("Yaw",   "mag"), ("Ralt",  "mag"),
        ("dHdop", "gga"), ("dSNo",  "gga"),
        ("Sk",    "spc"), ("Su",    "spc"), ("Sth",   "spc"),
    ]
    hdr = ["Variable"] + [f"Session {s} (mean +/- std)" for s in snums]
    rows = []
    for col, src in COMPARE_VARS:
        vals = []
        any_data = False
        for r in results:
            df = r[src]
            if col not in df.columns or df[col].isna().all():
                vals.append("NO DATA")
            else:
                s = df[col].dropna()
                vals.append(f"{s.mean():.3f} +/- {s.std():.4f}")
                any_data = True
        if any_data:
            rows.append((col, *vals))
    print(ascii_table(hdr, rows))

    # Save compact comparison file
    comp_path = out_root / f"comparison_{'_'.join(snums)}.txt"
    comp_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"SESSION COMPARISON: {' vs '.join(snums)}",
        "",
        ascii_table(
            ["Sensor", "Full Name"] + [f"Session {s}" for s in snums],
            [
                (sensor, SENSOR_REFERENCE[sensor]["full_name"],
                 *[_sensor_status(r, sensor) for r in results])
                for sensor in SENSOR_REFERENCE
            ]
        ),
        "",
        ascii_table(hdr, rows),
    ]
    comp_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Comparison saved: {comp_path.relative_to(PROJECT_ROOT)}")
    print()


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

    # ── Determine sessions ─────────────────────────────────────────────────────
    if args:
        sessions = [int(a) for a in args]
    else:
        sessions = find_sessions(data_dir)
        if not sessions:
            print(f"ERROR: no EVT*.txt files found in {data_dir}")
            sys.exit(1)

    out_root = PROJECT_ROOT / "outputs"

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  STEP 1 - Sensor Status & Data Quality Check")
    print("=" * 72)
    print(f"\n  Data folder : {data_dir.relative_to(PROJECT_ROOT)}")
    print(f"  Sessions    : {sessions}")
    print(f"  Outputs     : {out_root.relative_to(PROJECT_ROOT)}/")

    print(f"\nFiles in data folder:")
    for f in sorted(data_dir.iterdir()):
        print(f"  {f.name}")

    # ── Run analysis for each session ──────────────────────────────────────────
    results = []
    for session_num in sessions:
        r = analyse_session(data_dir, session_num, out_root, plots=True)
        results.append(r)

    # ── Comparison (2 or more sessions) ───────────────────────────────────────
    if len(results) >= 2:
        _print_comparison(results, out_root)

    print()
    print("=" * 72)
    print(f"  Step 1 complete - {len(sessions)} session(s) processed.")
    print("=" * 72)


if __name__ == "__main__":
    main()
