"""
Module 1 — QC metric computations.

Only the 3 metrics that TestSurveyNav.csv actually defines a threshold for are
computed: altitude, cross-track deviation, and ground speed. No thresholds are
ever read from project.yaml.

Computed values:
    ralt_mean_m         mean radar altitude
    cross_track_max_m   max perpendicular distance from planned line
    speed_mean_kmh      mean ground speed

Pass/fail flags (threshold source: TestSurveyNav only):
    pass_altitude       mean Ralt within [RadarMin, RadarMax]
    pass_cross_track    cross_track_max_m <= CrossTrack
    pass_speed          mean speed within [GroundSpeedMin, GroundSpeedMax]
    pass_all            all three above
"""

import numpy as np
import pandas as pd
from pathlib import Path
from pyproj import Transformer


def _cross_track_m(df: pd.DataFrame, A: np.ndarray, unit: np.ndarray,
                   transformer: Transformer) -> np.ndarray:
    """Perpendicular distance from the planned A→B axis for each GPS point."""
    x, y  = transformer.transform(df['Xgps'].values, df['Ygps'].values)
    P     = np.column_stack([x, y])
    t     = (P - A) @ unit
    proj  = A + np.outer(t, unit)
    return np.sqrt(np.sum((P - proj) ** 2, axis=1))


def _ground_speed_kmh(df: pd.DataFrame) -> np.ndarray:
    """Ground speed in km/h from consecutive GPS points and M3clk timestamps."""
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dt_s = np.diff(df['M3clk'].values) / 1000.0
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    dist_m = 6371000.0 * np.sqrt(dlat ** 2 + (np.cos(lat_mid) * dlon) ** 2)
    valid = dt_s > 0.05           # ignore sub-50 ms intervals (duplicate timestamps)
    speed = np.full(len(dist_m), np.nan)
    speed[valid] = dist_m[valid] / dt_s[valid] * 3.6
    return speed


def compute_segment_metrics(
    seg: pd.DataFrame,
    A: np.ndarray,
    unit: np.ndarray,
    survey_thresholds: dict,
    transformer: Transformer,
) -> dict:
    """
    Compute the 3 TestSurveyNav-thresholded QC metrics for one
    (flight_id, line_id) segment.

        pass_altitude    : mean Ralt within [RadarMin, RadarMax]
        pass_cross_track : cross_track_max_m <= CrossTrack
        pass_speed       : mean speed within [GroundSpeedMin, GroundSpeedMax]
        pass_all         : all three above

    Parameters
    ----------
    seg               : DataFrame rows for this segment (line_valid=True)
    A, unit           : planned line origin and unit direction vector (UTM)
    survey_thresholds : output of read_survey_thresholds() from TestSurveyNav
    transformer        : pyproj Transformer WGS84→UTM
    """
    seg = seg.dropna(subset=['Xgps', 'Ygps']).sort_values('M3clk')
    if len(seg) < 2:
        return {}

    ralt_min  = survey_thresholds.get('radar_min_m',    80.0)
    ralt_max  = survey_thresholds.get('radar_max_m',   110.0)
    spd_min   = survey_thresholds.get('speed_min_kmh',  90.0)
    spd_max   = survey_thresholds.get('speed_max_kmh', 150.0)
    ct_limit  = survey_thresholds.get('cross_track_m',  50.0)

    m = {}

    # ---- Altitude (pass/fail: mean within TestSurveyNav band) --------------
    if 'Ralt' in seg.columns:
        ralt = seg['Ralt'].dropna().values
        m['ralt_mean_m']    = round(float(np.mean(ralt)), 1)
        m['pass_altitude']  = ralt_min <= m['ralt_mean_m'] <= ralt_max
    else:
        m.update(ralt_mean_m=np.nan, pass_altitude=None)

    # ---- Cross-track (pass/fail: max <= CrossTrack from TestSurveyNav) -----
    ct = _cross_track_m(seg, A, unit, transformer)
    m['cross_track_max_m']  = round(float(ct.max()),  1)
    m['pass_cross_track']   = m['cross_track_max_m'] <= ct_limit

    # ---- Ground speed (pass/fail: mean within TestSurveyNav band) ----------
    speed       = _ground_speed_kmh(seg)
    valid_speed = speed[~np.isnan(speed)]
    if len(valid_speed) > 0:
        m['speed_mean_kmh'] = round(float(np.nanmean(valid_speed)), 1)
        m['pass_speed']     = spd_min <= m['speed_mean_kmh'] <= spd_max
    else:
        m.update(speed_mean_kmh=np.nan, pass_speed=None)

    # ---- Overall pass (TestSurveyNav criteria only) ------------------------
    flags   = [m.get('pass_altitude'), m.get('pass_cross_track'), m.get('pass_speed')]
    defined = [f for f in flags if f is not None]
    m['pass_all'] = all(defined) if defined else None

    return m


def run_qc(
    selected: pd.DataFrame,
    interim_root: Path,
    survey_nav: pd.DataFrame,
    survey_thresholds: dict,
    projection: str,
) -> pd.DataFrame:
    """
    Compute QC metrics for all selected (flight_id, line_id) segments.

    Pass/fail thresholds come exclusively from survey_thresholds (TestSurveyNav).

    Parameters
    ----------
    selected          : rows from line_selection.csv where selected=True
    interim_root      : data/interim/<campaign>/<run_name>/
    survey_nav        : DataFrame from read_survey_nav
    survey_thresholds : dict from read_survey_thresholds (TestSurveyNav)
    projection        : UTM CRS string

    Returns
    -------
    DataFrame with one row per (flight_id, line_id) and all metric columns.
    """
    transformer = Transformer.from_crs('EPSG:4326', projection, always_xy=True)

    # Build planned line geometry index
    planned = {}
    for _, row in survey_nav.iterrows():
        lid = int(row['line_id'])
        A   = np.array([row['E_start'], row['N_start']])
        B   = np.array([row['E_end'],   row['N_end']])
        AB  = B - A
        length = np.linalg.norm(AB)
        unit   = AB / length if length > 0 else AB
        planned[lid] = (A, unit, length)

    rows = []
    for _, sel in selected.iterrows():
        date      = sel['date']
        flight_id = str(sel['flight_id'])
        line_id   = int(sel['line_id'])

        pq_path = interim_root / 'm00' / date / f'flight_{flight_id}_prepared.parquet'
        if not pq_path.exists():
            print(f"  Skipping {date}/{flight_id} line {line_id}: parquet not found")
            continue

        df  = pd.read_parquet(pq_path)
        seg = df[(df['line_id'] == line_id) & df['line_valid']].copy()
        if seg.empty:
            print(f"  Skipping line {line_id} in {flight_id}: no valid data")
            continue

        if line_id not in planned:
            print(f"  Warning: line {line_id} not in survey plan, skipping cross-track")
        A, unit, _ = planned.get(line_id, (np.zeros(2), np.array([1.0, 0.0]), 0))

        print(f"  QC {date}  flight {flight_id}  line {line_id} ...", end='  ')
        metrics = compute_segment_metrics(
            seg, A, unit, survey_thresholds, transformer,
        )
        if metrics:
            row = {'date': date, 'flight_id': flight_id, 'line_id': line_id}
            row.update(metrics)
            rows.append(row)
            status = 'PASS' if metrics.get('pass_all') else 'FAIL'
            print(status)

    return pd.DataFrame(rows)
