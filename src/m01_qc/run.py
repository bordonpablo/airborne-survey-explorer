"""
Module 1 — QC entry point.

Reads line_selection.csv, loads the prepared parquets for all selected
(flight_id, line_id) segments, computes QC metrics, saves a report CSV,
and opens a visualisation.

Modes
-----
No line_id  → summary: map of all tracks coloured by pass/fail + metric heatmap.
With line_id → detail: interactive threshold slider for a specific segment.

Usage
-----
    python -m src.m01_qc.run                                   # all selected lines
    python -m src.m01_qc.run 22.04.2022                        # one day
    python -m src.m01_qc.run 22.04.2022 00427                  # one flight
    python -m src.m01_qc.run 22.04.2022 00427 10010            # detail, Ralt
    python -m src.m01_qc.run 22.04.2022 00427 10010 Roll       # detail, Roll
"""

import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m00_preparation.read_survey_nav import read_survey_nav, read_survey_thresholds
from src.m01_qc.metrics import run_qc
from src.m01_qc.viz import summary_figure, detail_figure, DETAIL_VARS


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def load_line_selection(interim_root: Path) -> pd.DataFrame:
    path = interim_root / 'line_selection.csv'
    if not path.exists():
        raise FileNotFoundError(
            f"line_selection.csv not found at {path}\n"
            "Run build_line_selection.py first."
        )
    return pd.read_csv(path, dtype={'flight_id': str, 'line_id': int})


def filter_selection(
    df: pd.DataFrame,
    target_date: str | None,
    target_flight: str | None,
    target_line: int | None,
) -> pd.DataFrame:
    sel = df[df['selected'] == True].copy()
    if target_date:
        sel = sel[sel['date'] == target_date]
    if target_flight:
        sel = sel[sel['flight_id'] == target_flight]
    if target_line:
        sel = sel[sel['line_id'] == target_line]
    return sel.reset_index(drop=True)


def _build_gps_dict(selected: pd.DataFrame, interim_root: Path) -> dict:
    """Load GPS coordinates for all selected segments (for the summary map)."""
    gps_dict = {}
    for _, row in selected.iterrows():
        pq = interim_root / row['date'] / f"flight_{row['flight_id']}_prepared.parquet"
        if not pq.exists():
            continue
        df  = pd.read_parquet(pq, columns=['line_id', 'line_valid', 'Xgps', 'Ygps'])
        seg = df[(df['line_id'] == row['line_id']) & df['line_valid']]
        gps_dict[(str(row['flight_id']), int(row['line_id']), row['date'])] = seg
    return gps_dict


def main(
    target_date: str | None = None,
    target_flight: str | None = None,
    target_line: int | None = None,
    variable: str = 'Ralt',
) -> None:
    cfg      = load_config()
    campaign = cfg['campaign']['name']
    run_name = cfg['campaign']['run_name']
    proj     = cfg['campaign']['projection']
    nav_path = PROJECT_ROOT / cfg['campaign']['survey_nav_path']
    raw_root = PROJECT_ROOT / cfg['campaign']['raw_data_path']
    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
    out_root     = PROJECT_ROOT / 'outputs' / campaign / run_name / 'qc'

    thresholds        = cfg.get('m1', {})
    survey_nav        = read_survey_nav(nav_path)
    survey_thresholds = read_survey_thresholds(nav_path)

    print(f"Campaign : {campaign}")
    print(f"Run      : {run_name}")

    line_selection = load_line_selection(interim_root)
    selected       = filter_selection(line_selection, target_date, target_flight, target_line)

    if selected.empty:
        print("No selected lines match the given filters.")
        return

    print(f"Selected segments : {len(selected)}")

    # -------------------------------------------------------------------------
    # Detail mode (single line + interactive slider)
    # -------------------------------------------------------------------------
    if target_line is not None:
        row = selected.iloc[0]
        pq  = interim_root / row['date'] / f"flight_{row['flight_id']}_prepared.parquet"
        df  = pd.read_parquet(pq)
        seg = df[(df['line_id'] == target_line) & df['line_valid']].copy()
        if seg.empty:
            print(f"No valid data for line {target_line}.")
            return
        if variable not in seg.columns:
            available = [v for v in DETAIL_VARS if v in seg.columns]
            print(f"Variable '{variable}' not found. Available: {available}")
            return
        out_path = out_root / row['date'] / f"flight_{row['flight_id']}_line_{target_line}_{variable}.png"
        detail_figure(seg, variable, thresholds, survey_thresholds, out_path)
        return

    # -------------------------------------------------------------------------
    # Summary mode (all selected lines)
    # -------------------------------------------------------------------------
    print("Computing QC metrics...")
    qc_df = run_qc(
        selected, interim_root, raw_root,
        survey_nav, survey_thresholds, thresholds, proj,
    )

    if qc_df.empty:
        print("No metrics computed — check that parquets exist.")
        return

    # Print summary table
    pass_cols = [c for c in qc_df.columns if c.startswith('pass_')]
    print(f"\n{'─'*60}")
    print(qc_df[['date', 'flight_id', 'line_id'] + pass_cols].to_string(index=False))
    n_pass = int(qc_df['pass_all'].sum()) if 'pass_all' in qc_df.columns else 0
    print(f"\n  {n_pass} / {len(qc_df)} lines pass all QC checks.")
    print(f"{'─'*60}\n")

    # Save report
    scope = '_'.join(filter(None, [target_date, target_flight, 'qc_report']))
    report_path = out_root / f"{scope}.csv"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    qc_df.to_csv(report_path, index=False)
    print(f"  Report saved: {report_path}")

    # Summary figure
    gps_dict  = _build_gps_dict(selected, interim_root)
    fig_path  = out_root / f"{scope}.png"
    summary_figure(qc_df, gps_dict, fig_path)


if __name__ == '__main__':
    date_arg     = sys.argv[1] if len(sys.argv) > 1 else None
    flight_arg   = sys.argv[2].zfill(5) if len(sys.argv) > 2 else None
    line_arg     = int(sys.argv[3]) if len(sys.argv) > 3 else None
    variable_arg = sys.argv[4] if len(sys.argv) > 4 else 'Ralt'
    main(date_arg, flight_arg, line_arg, variable_arg)
