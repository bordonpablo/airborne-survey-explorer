"""
Module 0 — Data preparation entry point.

Usage:
    python -m src.m00_preparation.prepare
    python -m src.m00_preparation.prepare 22.04.2022
    python -m src.m00_preparation.prepare 22.04.2022 00427

Processes one or all flight days under the raw data folder defined in
config/project.yaml. For each flight found in a day folder, it:
  1. Reads MAG, GGA, SPC files
  2. Synchronises sensors onto the GGA time axis
  3. Trims line-end transients
  4. Saves to data/interim/<campaign>/<date>/flight_<N>_prepared.parquet
"""

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m00_preparation.read_mag import read_mag
from src.m00_preparation.read_gga import read_gga
from src.m00_preparation.read_spc import read_spc
from src.m00_preparation.sync_sensors import sync_sensors, trim_line_ends, save_prepared


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def find_flights(day_dir: Path) -> list[str]:
    """Return sorted list of flight IDs found in a day folder (from MAG files)."""
    return sorted(
        m.stem.replace('MAG', '').zfill(5)
        for m in day_dir.glob('MAG*.txt')
    )


def prepare_flight(day_dir: Path, flight_id: str, interim_dir: Path) -> None:
    date_str = day_dir.name

    mag_path = day_dir / f'MAG{flight_id}.txt'
    gga_path = day_dir / f'GGA{flight_id}.txt'
    spc_path = day_dir / f'SPC{flight_id}.txt'

    missing = [p for p in [mag_path, gga_path, spc_path] if not p.exists()]
    if missing:
        print(f"  Skipping {flight_id}: missing {[p.name for p in missing]}")
        return

    print(f"  Reading MAG{flight_id}...")
    mag = read_mag(mag_path, flight_id)
    print(f"  Reading GGA{flight_id}...")
    gga = read_gga(gga_path, flight_id)
    print(f"  Reading SPC{flight_id}...")
    spc = read_spc(spc_path, flight_id)

    print(f"  Synchronising sensors...")
    merged = sync_sensors(mag, gga, spc)
    trimmed = trim_line_ends(merged)

    n_lines = trimmed['line_id'].nunique()
    n_on_line = trimmed['line_id'].notna().sum()
    print(f"  {n_lines} survey lines, {n_on_line:,} on-line rows after trim")

    out_path = interim_dir / date_str / f'flight_{flight_id}_prepared.parquet'
    save_prepared(trimmed, out_path)


def main(target_date: str | None = None, target_flight: str | None = None) -> None:
    cfg = load_config()
    raw_root = PROJECT_ROOT / cfg['campaign']['raw_data_path']
    campaign = cfg['campaign']['name']
    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign

    if target_date:
        day_dirs = [raw_root / target_date]
    else:
        day_dirs = sorted(d for d in raw_root.iterdir() if d.is_dir())

    for day_dir in day_dirs:
        if not day_dir.exists():
            print(f"Day folder not found: {day_dir}")
            continue

        print(f"\n=== {day_dir.name} ===")
        flights = [target_flight] if target_flight else find_flights(day_dir)

        if not flights:
            print("  No MAG files found.")
            continue

        for fid in flights:
            prepare_flight(day_dir, fid, interim_root)


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    flight_arg = sys.argv[2].zfill(5) if len(sys.argv) > 2 else None
    main(date_arg, flight_arg)
