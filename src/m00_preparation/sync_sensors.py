"""
Sensor synchronisation for Module 0.

Merges MAG, GGA, and SPC DataFrames onto a common time axis using the system
clock values (M1clk / M2clk / M3clk), which are all milliseconds from the same
acquisition system start-up event.

Synchronisation strategy:
  - GGA is the primary axis (highest-accuracy differential GPS position).
  - MAG is merged onto GGA using merge_asof(direction='nearest', tolerance=200 ms).
    Both run at ~10 Hz so the nearest sample is at most ~50 ms away.
  - SPC is merged onto the result using tolerance=1500 ms.
    SPC runs at ~1 Hz, so each SPC reading covers ~10 MAG/GGA rows.

Line editing adds a boolean column 'line_valid' — data is never deleted:
  - line_id = NaN  → off-line row (transit or turn with blank Wayp): line_valid = False
  - line_id = int, line_valid = True  → on-line, passed all editing steps
  - line_id = int, line_valid = False → on-line but flagged (outside planned extent or corridor)

Editing steps applied in order:
  1. clip_to_line_extent — flags points that fall outside the planned start/end of the line.
     Uses along-track projection onto the planned line axis (geometric, not time-based).
  2. filter_by_cross_track — flags points farther than turn_filter_m from the planned line.
     Removes turns where the navigation system did not blank Wayp.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import Point, LineString

MAG_GGA_TOLERANCE_MS = 200
SPC_TOLERANCE_MS = 1500


def sync_sensors(
    mag: pd.DataFrame,
    gga: pd.DataFrame,
    spc: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge MAG, GGA and SPC onto the GGA time axis.

    Returns a single DataFrame with all sensor columns, sorted by M3clk.
    Rows from GGA with no matching MAG sample within tolerance have NaN
    for all MAG-derived columns.
    """
    mag_s = mag.dropna(subset=['M1clk']).sort_values('M1clk').reset_index(drop=True)
    gga_s = gga.dropna(subset=['M3clk']).sort_values('M3clk').reset_index(drop=True)
    spc_s = spc.dropna(subset=['M2clk']).sort_values('M2clk').reset_index(drop=True)

    merged = pd.merge_asof(
        gga_s, mag_s,
        left_on='M3clk', right_on='M1clk',
        direction='nearest',
        tolerance=MAG_GGA_TOLERANCE_MS,
        suffixes=('_gga', '_mag'),
    )

    merged = pd.merge_asof(
        merged, spc_s,
        left_on='M3clk', right_on='M2clk',
        direction='nearest',
        tolerance=SPC_TOLERANCE_MS,
        suffixes=('', '_spc'),
    )

    for col in ['flight_id', 'time_s']:
        gga_col = f'{col}_gga'
        mag_col = f'{col}_mag'
        if gga_col in merged.columns:
            merged[col] = merged[gga_col]
            merged = merged.drop(columns=[c for c in [gga_col, mag_col] if c in merged.columns])

    return merged.sort_values('M3clk').reset_index(drop=True)


def clip_to_line_extent(
    df: pd.DataFrame,
    survey_nav: pd.DataFrame,
    projection: str,
) -> pd.DataFrame:
    """
    Flag on-line points that fall outside the planned start/end of their survey line.

    For each (flight_id, line_id) segment, each GPS point is projected onto the
    axis of the planned line (A → B). The along-track coordinate t is:

        t = dot(P - A, unit(B - A))

    where P is the GPS point in UTM, A and B are the planned line endpoints.
    Points with t < 0 are before the start; t > |AB| are past the end.
    Both are flagged line_valid = False.

    This replaces time-based trimming with a geometric clip that respects the
    actual planned survey extent regardless of when Wayp was activated.

    Initialises 'line_valid': True for on-line rows, False for off-line rows.
    Rows with no valid GPS are left as-is.

    Parameters
    ----------
    df         : merged DataFrame from sync_sensors
    survey_nav : DataFrame from read_survey_nav
    projection : UTM CRS string (e.g. 'EPSG:32648')
    """
    transformer = Transformer.from_crs("EPSG:4326", projection, always_xy=True)

    planned = {}
    for _, row in survey_nav.iterrows():
        lid = int(row['line_id'])
        A = np.array([row['E_start'], row['N_start']])
        B = np.array([row['E_end'],   row['N_end']])
        AB = B - A
        length = np.linalg.norm(AB)
        unit = AB / length if length > 0 else AB
        planned[lid] = (A, unit, length)

    df = df.copy()
    on_line = df['line_id'].notna()
    df['line_valid'] = False
    df.loc[on_line, 'line_valid'] = True

    for (fid, lid), seg in df[on_line].groupby(['flight_id', 'line_id'], sort=False):
        lid_int = int(lid)
        if lid_int not in planned:
            continue

        A, unit, length = planned[lid_int]
        valid_gps = seg.dropna(subset=['Xgps', 'Ygps'])
        if valid_gps.empty:
            continue

        x_utm, y_utm = transformer.transform(
            valid_gps['Xgps'].values,
            valid_gps['Ygps'].values,
        )
        P = np.column_stack([x_utm, y_utm])
        t = (P - A) @ unit                          # along-track coordinate

        outside = (t < 0) | (t > length)
        df.loc[valid_gps.index[outside], 'line_valid'] = False

    return df


def filter_by_cross_track(
    df: pd.DataFrame,
    survey_nav: pd.DataFrame,
    tolerance_m: float,
    projection: str,
) -> pd.DataFrame:
    """
    Flag on-line rows farther than tolerance_m from the planned survey line.

    Applied after clip_to_line_extent. Catches turns where the navigation
    system kept Wayp active but the aircraft was laterally far from the line
    (e.g. the approach arc projects within the line extent but is off to the side).

    Only rows currently marked line_valid = True are re-evaluated; rows already
    flagged False are left unchanged.

    Parameters
    ----------
    df         : DataFrame from clip_to_line_extent (must have 'line_valid')
    survey_nav : DataFrame from read_survey_nav
    tolerance_m: max allowed perpendicular distance in metres
    projection : CRS of survey_nav coordinates (e.g. 'EPSG:32648')
    """
    transformer = Transformer.from_crs("EPSG:4326", projection, always_xy=True)

    planned = {
        int(row['line_id']): LineString([
            (row['E_start'], row['N_start']),
            (row['E_end'],   row['N_end']),
        ])
        for _, row in survey_nav.iterrows()
    }

    df = df.copy()
    currently_valid = df['line_id'].notna() & df['line_valid']

    for (fid, lid), seg in df[currently_valid].groupby(['flight_id', 'line_id'], sort=False):
        lid_int = int(lid)
        if lid_int not in planned:
            continue

        planned_line = planned[lid_int]
        valid_gps = seg.dropna(subset=['Xgps', 'Ygps'])
        if valid_gps.empty:
            continue

        x_utm, y_utm = transformer.transform(
            valid_gps['Xgps'].values,
            valid_gps['Ygps'].values,
        )
        distances = pd.Series(
            [Point(x, y).distance(planned_line) for x, y in zip(x_utm, y_utm)],
            index=valid_gps.index,
        )
        outside = distances > tolerance_m
        df.loc[valid_gps.index[outside], 'line_valid'] = False

    return df


def save_prepared(df: pd.DataFrame, output_path: Path | str) -> None:
    """Save the prepared DataFrame to a Parquet file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"Saved: {output_path}  ({len(df):,} rows)")
