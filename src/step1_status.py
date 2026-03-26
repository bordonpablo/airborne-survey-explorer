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
from geoduster_utils import PROJECT_ROOT, find_sessions, analyse_session

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
    print("  STEP 1 – Sensor Status & Data Quality Check")
    print("=" * 72)
    print(f"\n  Data folder : {data_dir.relative_to(PROJECT_ROOT)}")
    print(f"  Sessions    : {sessions}")
    print(f"  Outputs     : {out_root.relative_to(PROJECT_ROOT)}/")

    print(f"\nFiles in data folder:")
    for f in sorted(data_dir.iterdir()):
        print(f"  {f.name}")

    # ── Run analysis for each session ──────────────────────────────────────────
    for session_num in sessions:
        analyse_session(data_dir, session_num, out_root, plots=True)

    print()
    print("=" * 72)
    print(f"  Step 1 complete – {len(sessions)} session(s) processed.")
    print("=" * 72)


if __name__ == "__main__":
    main()
