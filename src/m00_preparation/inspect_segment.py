"""
Module 0 — Static segment inspection.

Loads a prepared parquet and prints a summary table plus one figure per survey
line with six panels: radar altitude, cross-track deviation, ground speed,
cross-angle deviation, Roll/Pitch, and Yaw. Figures are saved as PNG — no
interactive window opens.

This module answers one question only: was the line flown the way it was
planned? All six panels plot the actual flown values against the thresholds
TestSurveyNav.csv defines for that line (RadarHeight/Min/Max, CrossTrack,
GroundSpeedMin/Max, CrossAngle) or are flight-attitude context (Roll/Pitch/Yaw).
There is no magnetometer panel here on purpose — whether the *signal* that was
recorded is any good is a different question, answered per selected line in
Module 1 (src.m01_qc.run, detail mode) once line_selection.csv has settled
which flight covers which line.

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
from pyproj import Transformer

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m00_preparation.read_survey_nav import read_survey_nav, read_survey_thresholds
from src.m01_qc.metrics import _cross_track_m, _ground_speed_kmh


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def build_planned_index(survey_nav: pd.DataFrame) -> dict:
    """
    Build a lookup of planned line geometry: line_id -> (A, unit, bearing_deg).

    A, unit  : origin point and unit direction vector (UTM metres), same
               convention used by sync_sensors.clip_to_line_extent and
               m01_qc.metrics for cross-track.
    bearing_deg : compass bearing (0=N, 90=E) of the A→B axis, used to judge
                  heading deviation regardless of which direction (A→B or
                  B→A) the line was actually flown.
    """
    planned = {}
    for _, row in survey_nav.iterrows():
        lid = int(row['line_id'])
        A  = np.array([row['E_start'], row['N_start']])
        B  = np.array([row['E_end'],   row['N_end']])
        AB = B - A
        length = np.linalg.norm(AB)
        unit = AB / length if length > 0 else AB
        bearing = (np.degrees(np.arctan2(AB[0], AB[1])) + 360) % 360
        planned[lid] = (A, unit, bearing)
    return planned


def cross_angle_deg(yaw: np.ndarray, bearing_deg: float) -> np.ndarray:
    """
    Angular deviation (degrees, signed) of the actual heading from the
    planned line axis, allowing for either flight direction (A→B or B→A).

    E.g. a line planned at bearing 90° (due east) accepts headings near both
    90° and 270° as "on axis" — only the deviation from the nearer of the two
    counts, matching TestSurveyNav's CrossAngle tolerance.
    """
    def _wrap(a: np.ndarray) -> np.ndarray:
        return (a + 180) % 360 - 180

    diff_fwd = _wrap(yaw - bearing_deg)
    diff_rev = _wrap(yaw - ((bearing_deg + 180) % 360))
    return np.where(np.abs(diff_fwd) <= np.abs(diff_rev), diff_fwd, diff_rev)


def along_track_km(df: pd.DataFrame) -> np.ndarray:
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6371.0 * np.sqrt(dlat ** 2 + (np.cos(lat_mid) * dlon) ** 2)
    return np.concatenate([[0.0], np.cumsum(d)])


_COMPASS_POINTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
_COMPASS_ARROWS = {'N': '↑', 'NE': '↗', 'E': '→', 'SE': '↘',
                    'S': '↓', 'SW': '↙', 'W': '←', 'NW': '↖'}


def flight_heading(seg: pd.DataFrame) -> tuple[float, str, str]:
    """
    Initial great-circle bearing from the first to the last point of a line.

    The along-track x-axis always runs left-to-right in time order, but since
    consecutive production lines are flown in opposite directions (turn at
    each end), the same x-axis can mean East on one line and West on the
    next. This gives the compass direction so plots aren't ambiguous.

    Returns (bearing_deg, compass_point, arrow_glyph).
    """
    lon0, lat0 = np.radians(seg['Xgps'].iloc[0]), np.radians(seg['Ygps'].iloc[0])
    lon1, lat1 = np.radians(seg['Xgps'].iloc[-1]), np.radians(seg['Ygps'].iloc[-1])
    dlon = lon1 - lon0
    x = np.sin(dlon) * np.cos(lat1)
    y = np.cos(lat0) * np.sin(lat1) - np.sin(lat0) * np.cos(lat1) * np.cos(dlon)
    bearing = (np.degrees(np.arctan2(x, y)) + 360) % 360
    point = _COMPASS_POINTS[int((bearing + 22.5) // 45) % 8]
    return bearing, point, _COMPASS_ARROWS[point]


def print_summary(on_line: pd.DataFrame, flight_id: str, date: str) -> None:
    rows = []
    for lid, seg in on_line.groupby('line_id'):
        rows.append({
            'line_id':    int(lid),
            'n_points':   len(seg),
            'ralt_mean':  round(seg['Ralt'].mean(), 1) if 'Ralt' in seg.columns else None,
            'ralt_std':   round(seg['Ralt'].std(),  1) if 'Ralt' in seg.columns else None,
        })
    print(f"\nFlight {flight_id} — {date}  ({on_line['line_id'].nunique()} lines)\n")
    print(pd.DataFrame(rows).to_string(index=False))
    print()


def plot_line(
    seg: pd.DataFrame,
    survey_thresholds: dict,
    planned_geom: tuple | None,
    transformer: Transformer,
    out_path: Path,
) -> None:
    """
    Six-panel figure for one survey line — all navigation/flight-plan
    compliance, nothing about sensor signal quality:
      1. Radar altitude vs along-track distance         (RadarHeight/Min/Max)
      2. Cross-track deviation vs along-track distance   (CrossTrack)
      3. Ground speed vs along-track distance             (GroundSpeedMin/Max)
      4. Cross-angle deviation vs along-track distance    (CrossAngle)
      5. Roll and Pitch (lateral and longitudinal tilt of the aircraft)
      6. Yaw (heading — rotation around the vertical axis)

    Panels 1-4 plot the flown value against the corresponding TestSurveyNav.csv
    threshold for this line, so a spec violation is visible directly on the
    profile instead of only as a pass/fail flag. Panels 2 and 4 need the
    planned line geometry (planned_geom); if the line isn't in TestSurveyNav
    those two panels are left empty with a note.
    """
    seg  = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps'])
    dist = along_track_km(seg)
    bearing, compass, arrow = flight_heading(seg)

    fig, axes = plt.subplots(6, 1, figsize=(14, 16), sharex=True)
    fig.suptitle(
        f"Flight {seg['flight_id'].iloc[0]}  —  Line {int(seg['line_id'].iloc[0])}  "
        f"[{arrow} flown {compass}, bearing ~{bearing:.0f}°]",
        fontsize=13,
    )

    # ---- Panel 1: Radar altitude (RadarHeight/RadarMin/RadarMax) -----------
    ax = axes[0]
    if 'Ralt' in seg.columns:
        ax.plot(dist, seg['Ralt'].values, color='steelblue', linewidth=0.8, label='Ralt')
        r_height = survey_thresholds.get('radar_height_m')
        r_min    = survey_thresholds.get('radar_min_m')
        r_max    = survey_thresholds.get('radar_max_m')
        if r_height is not None:
            ax.axhline(r_height, color='green', linestyle='-', linewidth=0.9,
                       label=f'RadarHeight {r_height:.0f} m')
        if r_min is not None:
            ax.axhline(r_min, color='darkorange', linestyle='--', linewidth=0.8,
                       label=f'RadarMin {r_min:.0f} m')
        if r_max is not None:
            ax.axhline(r_max, color='red', linestyle='--', linewidth=0.8,
                       label=f'RadarMax {r_max:.0f} m')
    ax.set_ylabel('Radar altitude (m)')
    ax.legend(fontsize=7, loc='upper right', ncol=2)
    ax.grid(True, alpha=0.3)

    # ---- Panel 2: Cross-track deviation (CrossTrack) ------------------------
    ax = axes[1]
    ct_limit = survey_thresholds.get('cross_track_m')
    if planned_geom is not None:
        A, unit, _ = planned_geom
        ct = _cross_track_m(seg, A, unit, transformer)
        ax.plot(dist, ct, color='steelblue', linewidth=0.8, label='Cross-track')
        if ct_limit is not None:
            ax.axhline(ct_limit, color='red', linestyle='--', linewidth=0.8,
                       label=f'CrossTrack limit {ct_limit:.0f} m')
    else:
        ax.text(0.5, 0.5, 'Line not found in TestSurveyNav.csv — no planned axis to compare against',
                transform=ax.transAxes, ha='center', va='center', fontsize=8, color='gray')
    ax.set_ylabel('Cross-track (m)')
    ax.legend(fontsize=7, loc='upper right')
    ax.grid(True, alpha=0.3)

    # ---- Panel 3: Ground speed (GroundSpeedMin/Max) --------------------------
    ax = axes[2]
    spd = _ground_speed_kmh(seg)
    spd_min = survey_thresholds.get('speed_min_kmh')
    spd_max = survey_thresholds.get('speed_max_kmh')
    ax.plot(dist[1:], spd, color='steelblue', linewidth=0.8, label='Ground speed')
    if spd_min is not None:
        ax.axhline(spd_min, color='darkorange', linestyle='--', linewidth=0.8,
                   label=f'SpeedMin {spd_min:.0f} km/h')
    if spd_max is not None:
        ax.axhline(spd_max, color='red', linestyle='--', linewidth=0.8,
                   label=f'SpeedMax {spd_max:.0f} km/h')
    ax.set_ylabel('Ground speed (km/h)')
    ax.legend(fontsize=7, loc='upper right', ncol=3)
    ax.grid(True, alpha=0.3)

    # ---- Panel 4: Cross-angle deviation (CrossAngle) -------------------------
    ax = axes[3]
    ca_limit = survey_thresholds.get('cross_angle_deg')
    if planned_geom is not None and 'Yaw' in seg.columns:
        _, _, plan_bearing = planned_geom
        ca = cross_angle_deg(seg['Yaw'].values, plan_bearing)
        ax.plot(dist, ca, color='steelblue', linewidth=0.8, label='Cross-angle')
        if ca_limit is not None:
            ax.axhline(ca_limit, color='red', linestyle='--', linewidth=0.8,
                       label=f'CrossAngle limit ±{ca_limit:.0f}°')
            ax.axhline(-ca_limit, color='red', linestyle='--', linewidth=0.8)
        ax.axhline(0, color='gray', linewidth=0.5)
    else:
        ax.text(0.5, 0.5, 'Line not found in TestSurveyNav.csv — no planned axis to compare against',
                transform=ax.transAxes, ha='center', va='center', fontsize=8, color='gray')
    ax.set_ylabel('Cross-angle (°)')
    ax.legend(fontsize=7, loc='upper right')
    ax.grid(True, alpha=0.3)

    # ---- Panel 5: Roll and Pitch (aircraft tilt) ------------------------------
    ax = axes[4]
    for col, color in [('Roll', 'seagreen'), ('Pitch', 'mediumpurple')]:
        if col in seg.columns:
            ax.plot(dist, seg[col].values, color=color, linewidth=0.8, label=col)
    ax.axhline(0, color='gray', linewidth=0.5)
    ax.set_ylabel('Roll / Pitch (°)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # ---- Panel 6: Yaw (heading) -----------------------------------------------
    ax = axes[5]
    if 'Yaw' in seg.columns:
        ax.plot(dist, seg['Yaw'].values, color='darkorange', linewidth=0.8, label='Yaw')
    ax.set_ylabel('Yaw / heading (°)')
    ax.set_xlabel(f'Along-track distance (km)   —   {arrow} start → end, flying {compass}')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    start = seg.iloc[0]
    end   = seg.iloc[-1]
    ax.annotate(f"start\n{start['Ygps']:.4f}, {start['Xgps']:.4f}",
                xy=(0, 0), xycoords=('data', 'axes fraction'),
                xytext=(3, -38), textcoords='offset points',
                fontsize=7, color='dimgray', ha='left')
    ax.annotate(f"end\n{end['Ygps']:.4f}, {end['Xgps']:.4f}",
                xy=(dist[-1], 0), xycoords=('data', 'axes fraction'),
                xytext=(-3, -38), textcoords='offset points',
                fontsize=7, color='dimgray', ha='right')

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _inspect_flight(
    date: str,
    flight_id: str,
    line_id: int | None,
    campaign: str,
    run_name: str,
    survey_thresholds: dict,
    planned: dict,
    transformer: Transformer,
) -> None:
    parquet_path = (
        PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
        / 'm00' / date / f'flight_{flight_id}_prepared.parquet'
    )
    if not parquet_path.exists():
        raise FileNotFoundError(f"Parquet not found: {parquet_path}\nRun prepare.py first.")

    df      = pd.read_parquet(parquet_path)
    on_line = df[df['line_id'].notna() & df['line_valid']].copy()

    if line_id is not None:
        on_line = on_line[on_line['line_id'] == line_id]
        if on_line.empty:
            raise ValueError(f"No valid data for line {line_id} in flight {flight_id}.")

    out_base = PROJECT_ROOT / 'outputs' / campaign / run_name / 'm00' / date / 'inspection'
    print_summary(on_line, flight_id, date)

    for lid, seg in on_line.groupby('line_id'):
        out_path = out_base / f"flight_{flight_id}_line_{int(lid)}.png"
        plot_line(seg, survey_thresholds, planned.get(int(lid)), transformer, out_path)


def inspect(date: str, flight_id: str | None = None, line_id: int | None = None) -> None:
    """
    Inspect one flight, or every flight prepared for that day if flight_id is
    omitted (mirrors the no-flight-id convention of prepare.py / export_qgis.py).
    """
    cfg        = load_config()
    campaign   = cfg['campaign']['name']
    run_name   = cfg['campaign']['run_name']
    nav_path   = PROJECT_ROOT / cfg['campaign']['survey_nav_path']
    projection = cfg['campaign']['projection']

    survey_thresholds = read_survey_thresholds(nav_path)
    planned           = build_planned_index(read_survey_nav(nav_path))
    transformer       = Transformer.from_crs('EPSG:4326', projection, always_xy=True)

    if flight_id is not None:
        flight_ids = [flight_id]
    else:
        day_dir = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name / 'm00' / date
        flight_ids = sorted(
            p.stem.replace('flight_', '').replace('_prepared', '')
            for p in day_dir.glob('flight_*_prepared.parquet')
        )
        if not flight_ids:
            print(f"No prepared parquets found for {date} under {day_dir}")
            return
        print(f"Found {len(flight_ids)} flight(s) for {date}: {', '.join(flight_ids)}")

    for fid in flight_ids:
        _inspect_flight(date, fid, line_id, campaign, run_name,
                        survey_thresholds, planned, transformer)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m src.m00_preparation.inspect_segment <date> [flight_id] [line_id]")
        sys.exit(1)
    date_arg   = sys.argv[1]
    flight_arg = sys.argv[2].zfill(5) if len(sys.argv) > 2 else None
    line_arg   = int(sys.argv[3]) if len(sys.argv) > 3 else None
    inspect(date_arg, flight_arg, line_arg)
