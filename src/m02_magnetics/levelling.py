"""
Module 2 — Step 7: Tie-line levelling.

After all sensor and field corrections, small DC offsets remain between adjacent
production lines, caused by residual heading errors, micro-variations in aircraft
magnetic signature, and imperfect corrections. These offsets appear as a
'washboard' pattern on the final map.

Tie-line levelling removes them by using N-S tie lines as a spatial reference:
at each crossover point, the difference between the production line value and
the tie line value gives the local offset for that production line.

Algorithm (standard crossover levelling)
-----------------------------------------
1. Classify all lines by heading: E-W = production, N-S = tie lines.
2. For each (production_line, tie_line) pair, estimate the crossover location:
       lon_cross ≈ median longitude of the tie line
       lat_cross ≈ median latitude of the production line
3. Interpolate Mag_IGRF_head from both lines at the crossover location.
4. Compute the crossover difference:
       diff = value_production - value_tie
5. For each production line, the correction is the mean of all its crossover
   differences (tie lines are held fixed as reference):
       δᵢ = mean(diff) over all tie lines crossing line i
6. Apply: Mag_IGRF_head_level = Mag_IGRF_head − δᵢ

Limitation — missing eastern tie lines
---------------------------------------
The Mongolia 2022 survey is missing 5 tie lines at the eastern edge (see
specialist report, Wackerle/Geointrepid). Production lines that only have
crossovers with the available (western/central) tie lines receive corrections
based on those crossovers only. Lines with NO crossover at all receive no
correction (δᵢ = 0). This may leave residual artefacts at the eastern edge.

The specialist addressed this by creating artificial tie lines from microlevelled
grids. That approach is not implemented here; microlevelling (step 8) is expected
to attenuate any remaining line-parallel artefacts.

Adds columns
------------
    Mag_IGRF_head_level : production-line field after levelling (nT)
    level_offset_nT     : the DC offset applied to each sample (0 for tie lines)
"""

import numpy as np
import pandas as pd


def _classify_heading(yaw_series: pd.Series) -> str:
    """Return 'EW', 'NS', or 'ND' for a line based on its mean Yaw."""
    yaw = yaw_series.dropna().values
    if len(yaw) == 0:
        return 'ND'
    rad = np.radians(yaw % 360)
    mean_deg = float(np.degrees(
        np.arctan2(np.nanmean(np.sin(rad)), np.nanmean(np.cos(rad)))
    )) % 360
    if 45 <= mean_deg < 135 or 225 <= mean_deg < 315:
        return 'EW'
    if mean_deg < 45 or mean_deg >= 315 or 135 <= mean_deg < 225:
        return 'NS'
    return 'ND'


def _interpolate_at(seg: pd.DataFrame, coord_col: str, coord_val: float,
                    value_col: str) -> float | None:
    """
    Interpolate value_col at coord_val along coord_col using the two nearest
    samples. Returns None if no valid data within 2× the median sample spacing.
    """
    seg = seg.dropna(subset=[coord_col, value_col]).sort_values(coord_col)
    if len(seg) < 2:
        return None

    x = seg[coord_col].values
    y = seg[value_col].values

    spacing = float(np.median(np.abs(np.diff(x))))
    if abs(coord_val - x).min() > 2 * spacing:
        return None

    return float(np.interp(coord_val, x, y))


def compute_crossover_offsets(
    df_all: pd.DataFrame,
    col: str = 'Mag_IGRF_head',
) -> pd.DataFrame:
    """
    Compute per-production-line DC offsets from crossover differences.

    Parameters
    ----------
    df_all : concatenated DataFrame of all lines with columns
             line_id, flight_id, Xgps, Ygps, Yaw, and col
    col    : magnetic column to use (default: Mag_IGRF_head)

    Returns
    -------
    DataFrame with columns: line_id, flight_id, direction, n_crossovers,
    mean_diff_nT, offset_nT.
    offset_nT is the correction to subtract from each production line.
    """
    if col not in df_all.columns:
        raise ValueError(f"Column '{col}' not found in DataFrame.")

    # Classify lines
    line_info = []
    for (fid, lid), seg in df_all.groupby(['flight_id', 'line_id']):
        if 'Yaw' not in seg.columns:
            continue
        direction = _classify_heading(seg['Yaw'])
        line_info.append({
            'flight_id': fid,
            'line_id':   lid,
            'direction': direction,
            'lat_med':   float(seg['Ygps'].median()),
            'lon_med':   float(seg['Xgps'].median()),
        })

    lines_df = pd.DataFrame(line_info)
    ew_lines = lines_df[lines_df['direction'] == 'EW']
    ns_lines = lines_df[lines_df['direction'] == 'NS']

    print(f"  [LEVEL] Production lines (EW): {len(ew_lines)}")
    print(f"  [LEVEL] Tie lines (NS)       : {len(ns_lines)}")

    if ns_lines.empty:
        print("  [LEVEL] No tie lines found — levelling cannot proceed.")
        return pd.DataFrame()

    # Compute crossover differences
    records = []
    for _, ew_row in ew_lines.iterrows():
        seg_ew = df_all[
            (df_all['flight_id'] == ew_row['flight_id']) &
            (df_all['line_id']   == ew_row['line_id'])
        ].copy()

        diffs = []
        for _, ns_row in ns_lines.iterrows():
            seg_ns = df_all[
                (df_all['flight_id'] == ns_row['flight_id']) &
                (df_all['line_id']   == ns_row['line_id'])
            ].copy()

            # Crossover location
            lon_cross = ns_row['lon_med']
            lat_cross = ew_row['lat_med']

            val_ew = _interpolate_at(seg_ew, 'Xgps', lon_cross, col)
            val_ns = _interpolate_at(seg_ns, 'Ygps', lat_cross, col)

            if val_ew is not None and val_ns is not None:
                diffs.append(val_ew - val_ns)

        if diffs:
            mean_diff = float(np.mean(diffs))
            records.append({
                'flight_id':    ew_row['flight_id'],
                'line_id':      ew_row['line_id'],
                'direction':    'EW',
                'n_crossovers': len(diffs),
                'mean_diff_nT': mean_diff,
                'offset_nT':    mean_diff,
            })
            print(f"  [LEVEL]   Line {int(ew_row['line_id'])} "
                  f"({len(diffs)} crossovers): offset = {mean_diff:+.3f} nT")
        else:
            records.append({
                'flight_id':    ew_row['flight_id'],
                'line_id':      ew_row['line_id'],
                'direction':    'EW',
                'n_crossovers': 0,
                'mean_diff_nT': 0.0,
                'offset_nT':    0.0,
            })
            print(f"  [LEVEL]   Line {int(ew_row['line_id'])}: no crossovers found")

    return pd.DataFrame(records)


def apply_levelling(
    df: pd.DataFrame,
    offsets: pd.DataFrame,
    col: str = 'Mag_IGRF_head',
) -> pd.DataFrame:
    """
    Apply per-line DC offsets to production lines.

    Parameters
    ----------
    df      : flight DataFrame
    offsets : output of compute_crossover_offsets
    col     : column to correct (default: Mag_IGRF_head)
    """
    df = df.copy()
    df['level_offset_nT']     = 0.0
    df['Mag_IGRF_head_level'] = df[col] if col in df.columns else np.nan

    if offsets.empty:
        return df

    for _, row in offsets.iterrows():
        mask = (df['flight_id'] == row['flight_id']) & (df['line_id'] == row['line_id'])
        if mask.any():
            df.loc[mask, 'level_offset_nT']     = row['offset_nT']
            df.loc[mask, 'Mag_IGRF_head_level'] = df.loc[mask, col] - row['offset_nT']

    return df
