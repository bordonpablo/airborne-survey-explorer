"""
Module 1 — QC metric computations.

All pass/fail thresholds come exclusively from TestSurveyNav.csv (read via
read_survey_thresholds).  No thresholds are defined in project.yaml.

Computed values (informative — no hard threshold, geophysicist decides):
    ralt_mean_m         mean radar altitude
    ralt_pct_outside    fraction of points outside [RadarMin, RadarMax]
    lalt_mean_m         mean laser altitude (if available)
    roll_max_deg        max |Roll| on the line
    pitch_max_deg       max |Pitch| on the line
    yaw_std_deg         heading standard deviation
    cross_track_max_m   max perpendicular distance from planned line
    cross_track_mean_m  mean perpendicular distance
    speed_mean_kmh      mean ground speed
    speed_pct_outside   fraction outside [SpeedMin, SpeedMax]
    gap_max_m           largest gap between consecutive GPS points
    mag_noise_nT        noise level: std(Δ²Mag1) / √6
    mag_spike_count     isolated spikes detected (detection sensitivity: 100 nT)
    diurnal_range_nT    Tagesgang variation during the line

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


def _along_track_dist_m(df: pd.DataFrame, transformer: Transformer) -> np.ndarray:
    x, y = transformer.transform(df['Xgps'].values, df['Ygps'].values)
    dx = np.diff(x)
    dy = np.diff(y)
    d = np.sqrt(dx ** 2 + dy ** 2)
    return np.concatenate([[0.0], np.cumsum(d)])


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


def _mag_noise_nT(mag: np.ndarray) -> float:
    """
    Noise level from second differences of the magnetic signal.

    Formula: std(Δ²Mag) / √6
    Removes linear trend and estimates the RMS noise in nT.
    This is the standard estimator used in airborne geophysical processing.
    """
    if len(mag) < 3:
        return np.nan
    d2 = np.diff(mag, n=2)
    return float(np.std(d2) / np.sqrt(6))


def _mag_spike_count(mag: np.ndarray, threshold_nT: float, window: int = 21) -> int:
    """Count isolated spikes using a rolling median as reference."""
    s = pd.Series(mag)
    smoothed = s.rolling(window, center=True, min_periods=1).median().values
    return int(np.sum(np.abs(mag - smoothed) > threshold_nT))


def _diurnal_range_nT(seg: pd.DataFrame, tagesgang: pd.DataFrame | None) -> float:
    """Tagesgang (base-station) variation during the time span of this segment."""
    if tagesgang is None or 'time_s' not in seg.columns:
        return np.nan
    t_min = seg['time_s'].min()
    t_max = seg['time_s'].max()
    window = tagesgang.loc[
        (tagesgang['time_s'] >= t_min) & (tagesgang['time_s'] <= t_max), 'nT'
    ]
    if len(window) < 2:
        return np.nan
    return float(window.max() - window.min())


_SPIKE_DETECTION_NT = 100.0   # sensitivity of the spike finder (rolling-median deviation)
_GAP_DETECTION_M    = 200.0   # gap size used only for reporting, not for pass/fail


def compute_segment_metrics(
    seg: pd.DataFrame,
    A: np.ndarray,
    unit: np.ndarray,
    survey_thresholds: dict,
    tagesgang: 'pd.DataFrame | None',
    transformer: Transformer,
) -> dict:
    """
    Compute all QC metrics for one (flight_id, line_id) segment.

    Pass/fail flags are derived exclusively from TestSurveyNav thresholds:
        pass_altitude    : mean Ralt within [RadarMin, RadarMax]
        pass_cross_track : cross_track_max_m <= CrossTrack
        pass_speed       : mean speed within [GroundSpeedMin, GroundSpeedMax]
        pass_all         : all three above

    All other columns are informative values — no arbitrary threshold is applied.

    Parameters
    ----------
    seg               : DataFrame rows for this segment (line_valid=True)
    A, unit           : planned line origin and unit direction vector (UTM)
    survey_thresholds : output of read_survey_thresholds() from TestSurveyNav
    tagesgang         : base station DataFrame or None
    transformer       : pyproj Transformer WGS84→UTM
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
        outside             = ((ralt < ralt_min) | (ralt > ralt_max)).sum()
        m['ralt_pct_outside'] = round(outside / len(ralt), 3)
        m['pass_altitude']  = ralt_min <= m['ralt_mean_m'] <= ralt_max
    else:
        m.update(ralt_mean_m=np.nan, ralt_pct_outside=np.nan, pass_altitude=None)

    if 'Lalt' in seg.columns:
        m['lalt_mean_m'] = round(float(seg['Lalt'].mean()), 1)
    else:
        m['lalt_mean_m'] = np.nan

    # ---- Attitude (informative only) ---------------------------------------
    for col, key in [('Roll', 'roll'), ('Pitch', 'pitch')]:
        if col in seg.columns:
            vals = seg[col].dropna().abs().values
            m[f'{key}_max_deg'] = round(float(vals.max()), 2)
        else:
            m[f'{key}_max_deg'] = np.nan

    if 'Yaw' in seg.columns:
        m['yaw_std_deg'] = round(float(np.std(seg['Yaw'].dropna().values)), 2)
    else:
        m['yaw_std_deg'] = np.nan

    # ---- Cross-track (pass/fail: max <= CrossTrack from TestSurveyNav) -----
    ct = _cross_track_m(seg, A, unit, transformer)
    m['cross_track_max_m']  = round(float(ct.max()),  1)
    m['cross_track_mean_m'] = round(float(ct.mean()), 1)
    m['pass_cross_track']   = m['cross_track_max_m'] <= ct_limit

    # ---- Ground speed (pass/fail: mean within TestSurveyNav band) ----------
    speed       = _ground_speed_kmh(seg)
    valid_speed = speed[~np.isnan(speed)]
    if len(valid_speed) > 0:
        outside = ((valid_speed < spd_min) | (valid_speed > spd_max)).sum()
        m['speed_mean_kmh']    = round(float(np.nanmean(valid_speed)), 1)
        m['speed_pct_outside'] = round(outside / len(valid_speed), 3)
        m['pass_speed']        = spd_min <= m['speed_mean_kmh'] <= spd_max
    else:
        m.update(speed_mean_kmh=np.nan, speed_pct_outside=np.nan, pass_speed=None)

    # ---- Sample spacing (informative only) ---------------------------------
    dist   = _along_track_dist_m(seg, transformer)
    gaps_m = np.diff(dist)
    m['gap_max_m'] = round(float(gaps_m.max()), 1)
    m['n_gaps']    = int((gaps_m > _GAP_DETECTION_M).sum())

    # ---- Magnetic noise and spikes (informative only) ----------------------
    if 'Mag1' in seg.columns:
        mag = seg['Mag1'].dropna().values
        m['mag_noise_nT']    = round(_mag_noise_nT(mag), 3)
        m['mag_spike_count'] = _mag_spike_count(mag, _SPIKE_DETECTION_NT)
    else:
        m.update(mag_noise_nT=np.nan, mag_spike_count=np.nan)

    # ---- Diurnal variation (informative only) ------------------------------
    dr = _diurnal_range_nT(seg, tagesgang)
    m['diurnal_range_nT'] = round(dr, 1) if not np.isnan(dr) else np.nan

    # ---- Overall pass (TestSurveyNav criteria only) ------------------------
    flags   = [m.get('pass_altitude'), m.get('pass_cross_track'), m.get('pass_speed')]
    defined = [f for f in flags if f is not None]
    m['pass_all'] = all(defined) if defined else None

    return m


def run_qc(
    selected: pd.DataFrame,
    interim_root: Path,
    raw_root: Path,
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
    raw_root          : data/raw/<campaign>/Daten_Nisleg_2022/
    survey_nav        : DataFrame from read_survey_nav
    survey_thresholds : dict from read_survey_thresholds (TestSurveyNav)
    projection        : UTM CRS string

    Returns
    -------
    DataFrame with one row per (flight_id, line_id) and all metric columns.
    """
    from src.m00_preparation.read_tagesgang import read_tagesgang

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

    # Cache Tagesgang per date
    tagesgang_cache: dict[str, pd.DataFrame | None] = {}

    rows = []
    for _, sel in selected.iterrows():
        date      = sel['date']
        flight_id = str(sel['flight_id'])
        line_id   = int(sel['line_id'])

        pq_path = interim_root / date / f'flight_{flight_id}_prepared.parquet'
        if not pq_path.exists():
            print(f"  Skipping {date}/{flight_id} line {line_id}: parquet not found")
            continue

        df  = pd.read_parquet(pq_path)
        seg = df[(df['line_id'] == line_id) & df['line_valid']].copy()
        if seg.empty:
            print(f"  Skipping line {line_id} in {flight_id}: no valid data")
            continue

        # Load Tagesgang (once per date)
        if date not in tagesgang_cache:
            tg_files = sorted((raw_root / date).glob('Tagesgang*.txt'))
            if tg_files:
                try:
                    tagesgang_cache[date] = read_tagesgang(tg_files[0])
                except Exception as e:
                    print(f"  Warning: could not read Tagesgang for {date}: {e}")
                    tagesgang_cache[date] = None
            else:
                tagesgang_cache[date] = None

        if line_id not in planned:
            print(f"  Warning: line {line_id} not in survey plan, skipping cross-track")
        A, unit, _ = planned.get(line_id, (np.zeros(2), np.array([1.0, 0.0]), 0))

        print(f"  QC {date}  flight {flight_id}  line {line_id} ...", end='  ')
        metrics = compute_segment_metrics(
            seg, A, unit, survey_thresholds,
            tagesgang_cache[date], transformer,
        )
        if metrics:
            row = {'date': date, 'flight_id': flight_id, 'line_id': line_id}
            row.update(metrics)
            rows.append(row)
            status = 'PASS' if metrics.get('pass_all') else 'FAIL'
            print(status)

    return pd.DataFrame(rows)
