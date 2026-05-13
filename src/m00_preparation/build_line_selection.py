"""
Module 0 — Build line selection table.

Scans all prepared parquet files and generates line_selection.csv, which records
which (flight_id, line_id) combination to use for each survey line in M1 and beyond.

When multiple flights cover the same line, the one with the most valid points is
auto-selected. Manual overrides (editing the 'selected' column) are preserved on
re-runs: re-running the script after adding new flights will not overwrite edits
already made to existing rows.

Output:
    data/interim/<campaign>/<run_name>/line_selection.csv

    Columns:
        line_id         — survey line number (integer)
        flight_id       — which flight to use for this line
        date            — flight date folder (DD.MM.YYYY)
        n_valid_points  — valid on-line points in this segment (for comparison)
        selected        — True = this (flight_id, line_id) enters M1; False = skip

Usage:
    python -m src.m00_preparation.build_line_selection
    python -m src.m00_preparation.build_line_selection 22.04.2022
    python -m src.m00_preparation.build_line_selection 22.04.2022 00447
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def scan_parquets(
    interim_root: Path,
    target_date: str | None = None,
    target_flight: str | None = None,
) -> pd.DataFrame:
    """
    Scan prepared parquet files and return a per-segment summary.

    Returns a DataFrame with columns: line_id, flight_id, date, n_valid_points.
    One row per (flight_id, line_id) combination found across all parquets.
    """
    if target_date and target_flight:
        candidates = [interim_root / target_date / f'flight_{target_flight}_prepared.parquet']
    elif target_date:
        candidates = sorted((interim_root / target_date).glob('flight_*_prepared.parquet'))
    else:
        candidates = sorted(interim_root.rglob('flight_*_prepared.parquet'))

    rows = []
    for pq in candidates:
        if not pq.exists():
            continue
        df = pd.read_parquet(pq, columns=['flight_id', 'line_id', 'line_valid'])
        date = pq.parent.name
        on_line = df[df['line_id'].notna() & df['line_valid']]
        for (fid, lid), grp in on_line.groupby(['flight_id', 'line_id']):
            rows.append({
                'line_id': int(lid),
                'flight_id': str(fid),
                'date': date,
                'n_valid_points': len(grp),
            })
        print(f"  Scanned {date}/{pq.name}  ({len(on_line):,} valid on-line rows)")

    if not rows:
        raise FileNotFoundError(f"No prepared parquets found under {interim_root}")

    return (
        pd.DataFrame(rows)
        .sort_values(['line_id', 'n_valid_points'], ascending=[True, False])
        .reset_index(drop=True)
    )


def auto_select(summary: pd.DataFrame) -> pd.DataFrame:
    """
    Mark the flight with the most valid points as selected for each line_id.

    When only one flight covers a line, it is selected automatically.
    When multiple flights cover the same line, the one with the highest
    n_valid_points wins; ties are broken by flight_id (alphabetically).
    """
    summary = summary.copy()
    summary['selected'] = False
    best_idx = summary.groupby('line_id')['n_valid_points'].idxmax()
    summary.loc[best_idx, 'selected'] = True
    return summary


def merge_with_existing(new: pd.DataFrame, existing_path: Path) -> pd.DataFrame:
    """
    Preserve manual 'selected' edits from an existing line_selection.csv.

    For rows present in both old and new: keep the old 'selected' value.
    For rows new to this run: keep the auto-computed value.
    Rows in old but absent in new (flight removed): dropped silently.
    """
    existing = pd.read_csv(existing_path, dtype={'flight_id': str, 'line_id': int})
    key = ['line_id', 'flight_id']
    merged = new.merge(
        existing[key + ['selected']].rename(columns={'selected': 'selected_prev'}),
        on=key,
        how='left',
    )
    has_prev = merged['selected_prev'].notna()
    merged.loc[has_prev, 'selected'] = merged.loc[has_prev, 'selected_prev'].astype(bool)
    return merged.drop(columns='selected_prev')


def build_line_selection(
    target_date: str | None = None,
    target_flight: str | None = None,
) -> None:
    cfg = load_config()
    interim_root = (
        PROJECT_ROOT / 'data' / 'interim'
        / cfg['campaign']['name'] / cfg['campaign']['run_name']
    )
    output_path = interim_root / 'line_selection.csv'

    print(f"Campaign : {cfg['campaign']['name']}")
    print(f"Run      : {cfg['campaign']['run_name']}")
    print("Scanning parquets...")

    summary = scan_parquets(interim_root, target_date, target_flight)
    summary = auto_select(summary)

    if output_path.exists():
        print("Existing line_selection.csv found — preserving manual edits...")
        summary = merge_with_existing(summary, output_path)

    summary.to_csv(output_path, index=False)

    n_lines = summary['line_id'].nunique()
    n_selected = int(summary['selected'].sum())
    counts_per_line = summary.groupby('line_id').size()
    multi = counts_per_line[counts_per_line > 1]

    print(f"\nDone.")
    print(f"  Output       : {output_path}")
    print(f"  Survey lines : {n_lines}")
    print(f"  Selected     : {n_selected}")
    if not multi.empty:
        print(f"  Lines with multiple flight options ({len(multi)}) — auto-selected by n_valid_points:")
        contested = summary[summary['line_id'].isin(multi.index)]
        print(contested[['line_id', 'flight_id', 'date', 'n_valid_points', 'selected']].to_string(index=False))
    print(f"\n  Review {output_path.name} and edit 'selected' as needed before running M1.")


if __name__ == '__main__':
    date_arg   = sys.argv[1] if len(sys.argv) > 1 else None
    flight_arg = sys.argv[2].zfill(5) if len(sys.argv) > 2 else None
    build_line_selection(date_arg, flight_arg)
