"""
Module 3 — Etapa A: prepare SPC files for GammAn import.

Reads each raw SPC file, smooths Sralt / Sbaro / Stemp, and writes a new
SPC file in the same format with those three fields replaced. All other
columns — especially Sbin (the raw spectrum) — are copied unchanged.

One output file per flight, named flight_XXXXX_spc_gamman.txt, placed in
  data/interim/<campaign>/<run_name>/m03_gamman/input/<date>/

Usage
-----
    python -m src.m03_radiometry.run_a                  # all flights
    python -m src.m03_radiometry.run_a 02.05.2022       # one day
    python -m src.m03_radiometry.run_a 02.05.2022 00447 # one flight
"""

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m03_radiometry.export_gamman import export_gamman


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def main(
    target_date:   str | None = None,
    target_flight: str | None = None,
) -> None:
    cfg      = load_config()
    campaign = cfg['campaign']['name']
    run_name = cfg['campaign']['run_name']
    raw_root = PROJECT_ROOT / cfg['campaign']['raw_data_path']
    out_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name / 'm03_gamman' / 'input'

    rad_cfg      = cfg.get('radiometry', {})
    window_sralt = int(rad_cfg.get('smooth_window_sralt', 5))
    window_env   = int(rad_cfg.get('smooth_window_env',   5))

    print(f'Campaign     : {campaign}')
    print(f'Run          : {run_name}')
    print(f'Smooth Sralt : {window_sralt} s')
    print(f'Smooth env   : {window_env} s  (Sbaro, Stemp)')
    print(f'Output root  : {out_root.relative_to(PROJECT_ROOT)}')

    date_dirs = sorted(d for d in raw_root.iterdir() if d.is_dir())
    if target_date:
        date_dirs = [d for d in date_dirs if d.name == target_date]
    if not date_dirs:
        print('No date folders found.')
        return

    total_flights = 0
    total_rows    = 0

    for date_dir in date_dirs:
        date      = date_dir.name
        spc_files = sorted(date_dir.glob('SPC*.txt'))
        if target_flight:
            spc_files = [f for f in spc_files if target_flight in f.stem]
        if not spc_files:
            continue

        print(f'\n{date}  ({len(spc_files)} SPC file(s))')

        for spc_path in spc_files:
            stem      = spc_path.stem
            flight_id = stem[3:] if stem.upper().startswith('SPC') else stem
            out_dir   = out_root / date / f'flight_{flight_id}'

            print(f'  {spc_path.name}')

            try:
                gamman_path, decoded_path = export_gamman(
                    spc_path, out_dir, window_sralt, window_env,
                )
                print(f'    gamman  → {gamman_path.relative_to(PROJECT_ROOT)}')
                print(f'    decoded → {decoded_path.relative_to(PROJECT_ROOT)}')
                total_flights += 1
            except ValueError as e:
                print(f'    [skipped] {e}')

    print(f'\nDone.  {total_flights} flight(s)')
    print(f'Output: data/interim/{campaign}/{run_name}/m03_gamman/input/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='M3 Etapa A — prepare SPC for GammAn')
    parser.add_argument('date',   nargs='?', default=None,
                        help='One day only  (DD.MM.YYYY)')
    parser.add_argument('flight', nargs='?', default=None,
                        help='One flight only  (e.g. 00447)')
    args = parser.parse_args()
    main(target_date=args.date, target_flight=args.flight)
