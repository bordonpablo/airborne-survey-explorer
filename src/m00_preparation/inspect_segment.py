"""
Module 0 — Segment inspection.

Two modes depending on whether a line_id is supplied:

  No line_id  → static summary: one 3-panel figure per line (altitude, magnetics,
                attitude) saved as PNG + summary table printed to terminal.

  With line_id → interactive threshold figure: GPS track (left panel) and variable
                profile vs along-track distance (right panel). A slider sets the
                threshold; points that exceed it turn red in both panels live.
                Default variable: Ralt. Default threshold: RadarMax from TestSurveyNav.

Thresholds in TestSurveyNav are in feet for Radar* fields. This script converts
them to metres. Verify that Ralt in your MAG files is also in metres; if it is in
feet the reference lines will appear ~3x too high and you should remove the
conversion in read_survey_thresholds().

Usage:
    python -m src.m00_preparation.inspect_segment 22.04.2022 00447
    python -m src.m00_preparation.inspect_segment 22.04.2022 00447 1001
    python -m src.m00_preparation.inspect_segment 22.04.2022 00447 1001 Roll
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m00_preparation.read_survey_nav import read_survey_thresholds

# Variables available for interactive inspection and their axis labels
_VAR_LABELS = {
    'Ralt':  'Radar altitude (m)',
    'Lalt':  'Laser altitude (m)',
    'Mag1':  'Magnetometer 1 (nT)',
    'Mag2':  'Magnetometer 2 (nT)',
    'Roll':  'Roll (°)',
    'Pitch': 'Pitch (°)',
    'Yaw':   'Yaw (°)',
}


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def along_track_km(df: pd.DataFrame) -> np.ndarray:
    """Cumulative along-track distance in km from WGS84 lon/lat."""
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6371.0 * np.sqrt(dlat ** 2 + (np.cos(lat_mid) * dlon) ** 2)
    return np.concatenate([[0.0], np.cumsum(d)])


def _default_threshold(variable: str, thresholds: dict) -> float:
    defaults = {
        'Ralt':  thresholds.get('radar_max_m', 130),
        'Lalt':  thresholds.get('radar_max_m', 130),
        'Roll':  5.0,
        'Pitch': 5.0,
        'Yaw':   180.0,
        'Mag1':  None,
        'Mag2':  None,
    }
    val = defaults.get(variable)
    return val  # None means: set to data median, handled in caller


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------

def _inspect_interactive(
    seg: pd.DataFrame,
    variable: str,
    thresholds: dict,
    out_path: Path,
) -> None:
    from matplotlib.widgets import Slider

    seg = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps', variable])
    if seg.empty:
        print(f"  No valid data for variable '{variable}'.")
        return

    dist   = along_track_km(seg)
    vals   = seg[variable].values
    lon    = seg['Xgps'].values
    lat    = seg['Ygps'].values
    label  = _VAR_LABELS.get(variable, variable)
    flight = seg['flight_id'].iloc[0]
    lid    = int(seg['line_id'].iloc[0])

    init_thresh = _default_threshold(variable, thresholds)
    if init_thresh is None:
        init_thresh = float(np.nanmedian(vals))

    above = vals > init_thresh

    fig, (ax_map, ax_prof) = plt.subplots(1, 2, figsize=(16, 7))
    plt.subplots_adjust(bottom=0.14, wspace=0.3)
    fig.suptitle(f"Flight {flight}  —  Line {lid}  |  {label}", fontsize=12)

    # ---- Map panel ---------------------------------------------------------
    ok_col  = 'steelblue'
    bad_col = 'red'
    colors  = np.where(above, bad_col, ok_col)

    scat_map = ax_map.scatter(lon, lat, s=4, c=colors, linewidths=0)
    ax_map.set_xlabel('Longitude')
    ax_map.set_ylabel('Latitude')
    ax_map.set_title('GPS track  (red = exceeds threshold)')
    ax_map.set_aspect('equal')
    ax_map.grid(True, alpha=0.2)

    # ---- Profile panel -----------------------------------------------------
    ax_prof.plot(dist, vals, color='lightsteelblue', linewidth=0.7, zorder=1)

    # Scatter only for bad points (updated on slider change)
    bad_xy = np.column_stack([dist[above], vals[above]]) if above.any() else np.empty((0, 2))
    scat_bad = ax_prof.scatter(
        bad_xy[:, 0] if bad_xy.size else [],
        bad_xy[:, 1] if bad_xy.size else [],
        s=10, c=bad_col, zorder=3,
    )

    thresh_line = ax_prof.axhline(
        init_thresh, color='red', linestyle='--', linewidth=1.2, label='Threshold'
    )

    # Reference lines for Ralt
    if variable in ('Ralt', 'Lalt'):
        rmin = thresholds.get('radar_min_m')
        rmax = thresholds.get('radar_max_m')
        if rmin:
            ax_prof.axhline(rmin, color='orange', linestyle=':', linewidth=1,
                            label=f'RadarMin {rmin:.0f} m')
        if rmax:
            ax_prof.axhline(rmax, color='darkred', linestyle=':', linewidth=1,
                            label=f'RadarMax {rmax:.0f} m')

    n_bad = int(above.sum())
    ax_prof.set_xlabel('Along-track distance (km)')
    ax_prof.set_ylabel(label)
    ax_prof.set_title(f'{n_bad} of {len(vals)} points exceed {init_thresh:.1f}')
    ax_prof.legend(fontsize=8)
    ax_prof.grid(True, alpha=0.3)

    # ---- Slider ------------------------------------------------------------
    val_min = float(np.nanmin(vals))
    val_max = float(np.nanmax(vals))
    ax_sl   = plt.axes([0.15, 0.04, 0.7, 0.03])
    slider  = Slider(ax_sl, label, val_min, val_max, valinit=init_thresh)

    def _update(val):
        thresh    = slider.val
        above_new = vals > thresh
        n         = int(above_new.sum())

        # Update map colors
        colors_new = np.where(above_new, bad_col, ok_col)
        scat_map.set_facecolors(colors_new)

        # Update bad scatter on profile
        if above_new.any():
            scat_bad.set_offsets(np.column_stack([dist[above_new], vals[above_new]]))
            scat_bad.set_visible(True)
        else:
            scat_bad.set_offsets(np.empty((0, 2)))
            scat_bad.set_visible(False)

        thresh_line.set_ydata([thresh, thresh])
        ax_prof.set_title(f'{n} of {len(vals)} points exceed {thresh:.1f}')
        fig.canvas.draw_idle()

    slider.on_changed(_update)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"  Saved: {out_path}")
    plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Static mode
# ---------------------------------------------------------------------------

def _plot_line_static(
    seg: pd.DataFrame,
    nominal_alt: float,
    out_path: Path,
) -> None:
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


def _print_summary(on_line: pd.DataFrame, flight_id: str, date: str) -> None:
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def inspect(
    date: str,
    flight_id: str,
    line_id: int | None = None,
    variable: str = 'Ralt',
) -> None:
    cfg         = load_config()
    campaign    = cfg['campaign']['name']
    run_name    = cfg['campaign']['run_name']
    nominal_alt = cfg['survey_design']['nominal_altitude_m']
    nav_path    = PROJECT_ROOT / cfg['campaign']['survey_nav_path']

    parquet_path = (
        PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
        / date / f'flight_{flight_id}_prepared.parquet'
    )
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}\nRun prepare.py first.")

    thresholds = read_survey_thresholds(nav_path)
    df         = pd.read_parquet(parquet_path)
    on_line    = df[df['line_id'].notna() & df['line_valid']].copy()

    out_base = PROJECT_ROOT / 'outputs' / campaign / run_name / 'inspection' / date

    if line_id is not None:
        # Interactive mode — single line
        seg = on_line[on_line['line_id'] == line_id]
        if seg.empty:
            raise ValueError(f"No valid data for line {line_id} in flight {flight_id}.")
        if variable not in seg.columns:
            raise ValueError(
                f"Variable '{variable}' not found. Available: {[c for c in _VAR_LABELS if c in seg.columns]}"
            )
        out_path = out_base / f"flight_{flight_id}_line_{line_id}_{variable}.png"
        _inspect_interactive(seg, variable, thresholds, out_path)
    else:
        # Static mode — all lines
        _print_summary(on_line, flight_id, date)
        for lid, seg in on_line.groupby('line_id'):
            out_path = out_base / f"flight_{flight_id}_line_{int(lid)}_static.png"
            _plot_line_static(seg, nominal_alt, out_path)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python -m src.m00_preparation.inspect_segment <date> <flight_id> [line_id] [variable]")
        print("       variable options:", ', '.join(_VAR_LABELS))
        sys.exit(1)
    date_arg     = sys.argv[1]
    flight_arg   = sys.argv[2].zfill(5)
    line_arg     = int(sys.argv[3])   if len(sys.argv) > 3 else None
    variable_arg = sys.argv[4]        if len(sys.argv) > 4 else 'Ralt'
    inspect(date_arg, flight_arg, line_arg, variable_arg)
