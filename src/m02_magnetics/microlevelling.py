"""
Module 2 — Step 8: Micro-levelling (decorrugation).

After tie-line levelling, short-wavelength line-parallel stripes often remain.
These are caused by small heading-dependent effects that vary rapidly along the
flight line and cannot be captured by a single DC offset per line. They appear
as a washboard or corrugation pattern on the final map.

Micro-levelling removes them by estimating and subtracting the corrugation
component of each line.

Algorithm
---------
The corrugation is the part of the signal that correlates with the survey line
direction but not with the across-line trend:

    1. For each production line, compute the along-line smooth:
           smooth_i(x) = moving_average( Mag_IGRF_head_level_i(x), window=W )
       where W = cutoff_wavelength / sample_spacing.
       This preserves long-wavelength geology while capturing the line DC trend.

    2. For each sample at position (x, y), compute the across-line trend by
       interpolating the smooth values from the two adjacent lines (N and S
       neighbors in latitude) at the same longitude x:
           trend(x, y) = mean( smooth_{i-1}(x), smooth_{i+1}(x) )

    3. The corrugation is the difference between the line smooth and the
       across-line trend:
           corrugation_i(x) = smooth_i(x) − trend(x, y)

    4. Remove the corrugation from the original data:
           Mag_Final = Mag_IGRF_head_level − corrugation_i(x)

Parameter
---------
cutoff_wavelength_m : low-pass cutoff along the line (default = 4 × line_spacing).
    Controls what counts as "corrugation" vs "geology":
    - Too short → geological features removed as corrugation
    - Too long  → corrugation not fully suppressed
    Typical values: 3–5 × line_spacing. Comes from project.yaml (line_spacing_m).

Limitation
----------
Only the two immediate neighbors are used for the across-line trend. Lines at
the survey edges (northernmost and southernmost) only have one neighbor and
receive a less constrained correction. The eastern-edge issue from missing tie
lines (see levelling.py) may leave some residual artefacts that micro-levelling
can attenuate but not fully remove.

Adds column
-----------
    Mag_Final : Residual Magnetic Anomaly after all corrections (nT)
"""

import numpy as np
import pandas as pd


def _moving_average(x: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average; edge effects handled by padding."""
    if window < 2:
        return x.copy()
    pad = window // 2
    padded = np.pad(x.astype(float), pad, mode='edge')
    kernel = np.ones(window) / window
    smooth = np.convolve(padded, kernel, mode='valid')
    return smooth[:len(x)]


def _sample_spacing_m(lons: np.ndarray, lats: np.ndarray) -> float:
    """Estimate median sample spacing in metres from lon/lat arrays."""
    dlat = np.diff(np.radians(lats))
    dlon = np.diff(np.radians(lons))
    lat_mid = np.radians(lats[:-1])
    d = 6_371_000.0 * np.sqrt(dlat**2 + (np.cos(lat_mid) * dlon)**2)
    return float(np.median(d[d > 0])) if len(d) > 0 else 10.0


def apply_microlevelling(
    df_all: pd.DataFrame,
    line_spacing_m: float,
    cutoff_wavelength_m: float | None = None,
    col: str = 'Mag_IGRF_head_level',
) -> pd.DataFrame:
    """
    Apply micro-levelling to all production lines and return a DataFrame
    with the new column Mag_Final added.

    Must be called with ALL production lines concatenated — the across-line
    trend requires neighboring lines to be present.

    Parameters
    ----------
    df_all              : concatenated DataFrame of all selected line segments
    line_spacing_m      : nominal line spacing (from project.yaml)
    cutoff_wavelength_m : along-line low-pass cutoff (default = 4 × line_spacing_m)
    col                 : input column (default: Mag_IGRF_head_level)
    """
    if cutoff_wavelength_m is None:
        cutoff_wavelength_m = 4.0 * line_spacing_m

    df_all = df_all.copy()
    df_all['Mag_Final'] = np.nan

    if col not in df_all.columns:
        print(f"  [MICROLEV] Column '{col}' not found — skipping.")
        return df_all

    # ── Step 1: along-line smooth for each production line ────────────────────
    line_smooths: dict[tuple, dict] = {}

    for (fid, lid), seg in df_all.groupby(['flight_id', 'line_id']):
        seg_s = seg.dropna(subset=['Xgps', 'Ygps', col]).sort_values('Xgps')
        if len(seg_s) < 5:
            continue

        spacing_m = _sample_spacing_m(seg_s['Xgps'].values, seg_s['Ygps'].values)
        window    = max(3, int(round(cutoff_wavelength_m / spacing_m)))
        smooth    = _moving_average(seg_s[col].values, window)

        line_smooths[(fid, lid)] = {
            'lons':    seg_s['Xgps'].values,
            'smooth':  smooth,
            'lat_med': float(seg_s['Ygps'].median()),
            'idx':     seg_s.index,
        }

    if not line_smooths:
        print("  [MICROLEV] No valid lines — skipping.")
        return df_all

    # Sort lines by latitude (N→S)
    sorted_keys = sorted(line_smooths.keys(), key=lambda k: line_smooths[k]['lat_med'])
    print(f"  [MICROLEV] Lines processed  : {len(sorted_keys)}")
    print(f"  [MICROLEV] Cutoff wavelength: {cutoff_wavelength_m:.0f} m")

    # ── Step 2 & 3: across-line trend and corrugation per line ───────────────
    for i, key in enumerate(sorted_keys):
        info   = line_smooths[key]
        lons   = info['lons']
        smooth = info['smooth']
        idx    = info['idx']

        # Find neighbors
        neighbors = []
        if i > 0:
            neighbors.append(line_smooths[sorted_keys[i - 1]])
        if i < len(sorted_keys) - 1:
            neighbors.append(line_smooths[sorted_keys[i + 1]])

        if not neighbors:
            corrugation = np.zeros(len(lons))
        else:
            across = np.zeros((len(neighbors), len(lons)))
            for j, nb in enumerate(neighbors):
                across[j] = np.interp(lons, nb['lons'], nb['smooth'],
                                       left=nb['smooth'][0], right=nb['smooth'][-1])
            trend       = across.mean(axis=0)
            corrugation = smooth - trend

        # ── Step 4: apply correction to original data ─────────────────────────
        orig_vals = df_all.loc[idx, col].values
        # Align corrugation to original (unsorted) index order
        seg_orig = df_all.loc[idx].sort_values('Xgps')
        corr_aligned = np.interp(
            df_all.loc[idx, 'Xgps'].values,
            seg_orig['Xgps'].values,
            corrugation[np.argsort(np.argsort(df_all.loc[idx, 'Xgps'].values))],
        )
        df_all.loc[idx, 'Mag_Final'] = orig_vals - corr_aligned

    n_valid = df_all['Mag_Final'].notna().sum()
    rms_corr = float(np.sqrt(np.nanmean(
        (df_all['Mag_Final'] - df_all[col]).dropna()**2
    ))) if col in df_all.columns else 0.0
    print(f"  [MICROLEV] Valid samples    : {n_valid:,}")
    print(f"  [MICROLEV] RMS corrugation  : {rms_corr:.4f} nT")

    return df_all
