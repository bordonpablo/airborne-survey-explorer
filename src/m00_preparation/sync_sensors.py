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
  - line_id = int, line_valid = False → on-line but flagged (transient or outside corridor)

Editing steps:
  1. trim_line_ends — flags the first/last N seconds of each segment.
  2. filter_by_cross_track — flags points farther than tolerance_m from the
     planned line (turns where the navigation system did not blank Wayp).
"""

import pandas as pd
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import Point, LineString

TRIM_SECONDS = 5.0
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


def trim_line_ends(df: pd.DataFrame, seconds: float = TRIM_SECONDS) -> pd.DataFrame:
    """
    Flag the first and last N seconds of each (flight_id, line_id) segment.

    Initialises 'line_valid' to True for all on-line rows and False for all
    off-line rows, then sets it to False for the transient rows at each end.
    """
    df = df.copy()
    on_line = df['line_id'].notna()
    df['line_valid'] = False                   # off-line rows start as False
    df.loc[on_line, 'line_valid'] = True       # on-line rows start as True

    for (fid, lid), seg in df[on_line].groupby(['flight_id', 'line_id'], sort=False):
        t = seg['time_s']
        transient = (t < t.iloc[0] + seconds) | (t > t.iloc[-1] - seconds)
        df.loc[seg.index[transient], 'line_valid'] = False

    return df


def filter_by_cross_track(
    df: pd.DataFrame,
    survey_nav: pd.DataFrame,
    tolerance_m: float,
    projection: str,
) -> pd.DataFrame:
    """
    Flag on-line rows that are farther than tolerance_m from the planned survey line.

    For each (flight_id, line_id) segment, finds the corresponding planned line
    in survey_nav and sets line_valid = False for GPS points whose perpendicular
    distance to that line exceeds tolerance_m. This flags turns where the
    navigation system did not blank Wayp before/after the manoeuvre.

    Rows with no valid GPS, or whose line_id is not found in survey_nav, are
    left unchanged.

    Parameters
    ----------
    df         : DataFrame from trim_line_ends (must have 'line_valid' column)
    survey_nav : DataFrame from read_survey_nav
    tolerance_m: corridor half-width in metres
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
    on_line = df['line_id'].notna()

    for (fid, lid), seg in df[on_line].groupby(['flight_id', 'line_id'], sort=False):
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
