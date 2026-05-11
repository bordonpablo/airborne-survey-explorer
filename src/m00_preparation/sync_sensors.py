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

After merging, rows where Wayp was blank in MAG (line_id = NaN) are retained
but clearly identifiable: they represent transits and turns between survey lines.

The trim step removes the first and last TRIM_SECONDS of each (flight_id, line_id)
segment to exclude alignment and pull-out transients.
"""

import pandas as pd
from pathlib import Path

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

    # Resolve duplicated columns from suffixes (flight_id, time_s)
    for col in ['flight_id', 'time_s']:
        gga_col = f'{col}_gga'
        mag_col = f'{col}_mag'
        if gga_col in merged.columns:
            merged[col] = merged[gga_col]
            merged = merged.drop(columns=[c for c in [gga_col, mag_col] if c in merged.columns])

    return merged.sort_values('M3clk').reset_index(drop=True)


def trim_line_ends(df: pd.DataFrame, seconds: float = TRIM_SECONDS) -> pd.DataFrame:
    """
    Remove the first and last N seconds of each (flight_id, line_id) segment.

    This discards alignment transients at the start of each line and
    pull-out manoeuvres at the end. Rows with line_id = NaN are kept as-is.
    """
    on_line = df['line_id'].notna()
    off_line = df[~on_line]

    trimmed_parts = []
    for (fid, lid), seg in df[on_line].groupby(['flight_id', 'line_id'], sort=False):
        t = seg['time_s']
        mask = (t >= t.iloc[0] + seconds) & (t <= t.iloc[-1] - seconds)
        trimmed_parts.append(seg[mask])

    if trimmed_parts:
        trimmed = pd.concat(trimmed_parts)
    else:
        trimmed = df[on_line].iloc[0:0]

    return pd.concat([trimmed, off_line]).sort_values('M3clk').reset_index(drop=True)


def save_prepared(df: pd.DataFrame, output_path: Path | str) -> None:
    """Save the prepared DataFrame to a Parquet file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"Saved: {output_path}  ({len(df):,} rows)")
