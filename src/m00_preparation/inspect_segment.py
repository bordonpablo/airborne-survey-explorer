"""
Module 0 — Static segment inspection.

Loads a prepared parquet and prints a summary table plus one 3-panel figure per
survey line (radar altitude, magnetometers, attitude). Use this for a quick
overview before editing line_selection.csv.

For interactive threshold exploration, use Module 1: src.m01_qc.run.

Usage:
    python -m src.m00_preparation.inspect_segment 22.04.2022 00427
    python -m src.m00_preparation.inspect_segment 22.04.2022 00427 10010
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def along_track_km(df: pd.DataFrame) -> np.ndarray:
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6371.0 * np.sqrt(dlat ** 2 + (np.cos(lat_mid) * dlon) ** 2)
    return np.concatenate([[0.0], np.cumsum(d)])


def print_summary(on_line: pd.DataFrame, flight_id: str, date: str) -> None:
    rows = []
    for lid, seg in on_line.groupby('line_id'):
        rows.append({
            'line_id':    int(lid),
            'n_points':   len(seg),
            'ralt_mean':  round(seg['Ralt'].mean(), 1) if 'Ralt' in seg.columns else None,
            'ralt_std':   round(seg['Ralt'].std(),  1) if 'Ralt' in seg.columns else None,
            'mag1_range': round(seg['Mag1'].max() - seg['Mag1'].min(), 1) if 'Mag1' in seg.columns else None,
        })
    print(f"\nFlight {flight_id} — {date}  ({on_line['line_id'].nunique()} lines)\n")
    print(pd.DataFrame(rows).to_string(index=False))
    print()


def plot_line(seg: pd.DataFrame, nominal_alt: float, out_path: Path) -> None:
    seg  = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps'])
    dist = along_track_km(seg)

    fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
    fig.suptitle(
        f"Flight {seg['flight_id'].iloc[0]}  —  Line {int(seg['line_id'].iloc[0])}",
        fontsize=13,
    )

    ax = axes[0]
    if 'Ralt' in seg.columns:
        ax.plot(dist, seg['Ralt'].values, color='steelblue', linewidth=0.8, label='Ralt')
        ax.axhline(nominal_alt, color='red', linestyle='--', linewidth=0.8,
                   label=f'Nominal {nominal_alt} m')
    ax.set_ylabel('Radar altitude (m)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    for col, color in [('Mag1', 'navy'), ('Mag2', 'darkorange')]:
        if col in seg.columns:
            ax.plot(dist, seg[col].values, color=color, linewidth=0.8, label=col)
    ax.set_ylabel('Magnetometer (nT)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    ax = axes[2]
    for col, color in [('Roll', 'seagreen'), ('Pitch', 'mediumpurple')]:
        if col in seg.columns:
            ax.plot(dist, seg[col].values, color=color, linewidth=0.8, label=col)
    ax.axhline(0, color='gray', linewidth=0.5)
    ax.set_ylabel('Attitude (°)')
    ax.set_xlabel('Along-track distance (km)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"  Saved: {out_path}")
    plt.show()
    plt.close(fig)


def inspect(date: str, flight_id: str, line_id: int | None = None) -> None:
    cfg         = load_config()
    campaign    = cfg['campaign']['name']
    run_name    = cfg['campaign']['run_name']
    nominal_alt = cfg['survey_design']['nominal_altitude_m']

    parquet_path = (
        PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
        / date / f'flight_{flight_id}_prepared.parquet'
    )
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}\nRun prepare.py first.")

    df      = pd.read_parquet(parquet_path)
    on_line = df[df['line_id'].notna() & df['line_valid']].copy()

    if line_id is not None:
        on_line = on_line[on_line['line_id'] == line_id]
        if on_line.empty:
            raise ValueError(f"No valid data for line {line_id} in flight {flight_id}.")

    out_base = PROJECT_ROOT / 'outputs' / campaign / run_name / 'inspection' / date
    print_summary(on_line, flight_id, date)

    for lid, seg in on_line.groupby('line_id'):
        out_path = out_base / f"flight_{flight_id}_line_{int(lid)}.png"
        plot_line(seg, nominal_alt, out_path)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python -m src.m00_preparation.inspect_segment <date> <flight_id> [line_id]")
        sys.exit(1)
    date_arg   = sys.argv[1]
    flight_arg = sys.argv[2].zfill(5)
    line_arg   = int(sys.argv[3]) if len(sys.argv) > 3 else None
    inspect(date_arg, flight_arg, line_arg)
