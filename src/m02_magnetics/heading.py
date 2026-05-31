"""
Module 2 — Step 5: Heading correction.

After the onboard compensation system removes the bulk of the aircraft's magnetic
interference, a small residual remains that depends on the aircraft's heading relative
to Earth's field. This shows up as a systematic offset between lines flown in opposite
directions (E vs W for E-W surveys).

Method: empirical DC correction by heading direction
-----------------------------------------------------
The rigorous approach (Tolles-Lawson, 16-term model) requires a dedicated calibration
flight. When no such flight is available, an empirical correction is applied:

    1. Classify every survey line by its mean heading direction (E or W).
    2. For each line, compute the mean of Mag1_IGRF (the line DC level).
    3. Compute the mean DC level for all E-flying lines (μ_E) and all W-flying
       lines (μ_W).
    4. The heading bias is half the difference:
           bias = (μ_E − μ_W) / 2
    5. Apply a constant offset per direction:
           E lines: Mag1_IGRF_head = Mag1_IGRF − bias
           W lines: Mag1_IGRF_head = Mag1_IGRF + bias

Rationale: if two adjacent antiparallel lines fly over the same geology, their
field difference can only come from heading-dependent aircraft interference. The
factor of 1/2 comes from the fact that both lines are equally offset from the
true geological value but in opposite directions.

Limitations
-----------
- Assumes the mean geological signal is the same for E and W lines across the
  survey. This holds for dense, regular surveys but can introduce errors in areas
  with strong geological gradients.
- Only corrects the DC (mean) component of the heading effect. High-frequency
  heading noise (e.g. from banking) is not addressed here.
- Tie lines (N-S) are not used in this implementation but could improve the
  correction by providing independent crossover-based estimates.

Adds columns
------------
    Mag1_IGRF_head : Mag1_IGRF after heading correction (nT)
    Mag2_IGRF_head : Mag2_IGRF after heading correction (nT)
    heading_bias_nT: the bias value applied to each sample (positive for W lines)
"""

import numpy as np
import pandas as pd


def _classify_heading(yaw: np.ndarray) -> str:
    """
    Classify the mean heading of a line as 'E', 'W', 'N', 'S', or 'ND'.

    Uses circular mean of Yaw angles.
    """
    rad = np.radians(yaw % 360)
    mean_angle = float(np.degrees(np.arctan2(
        np.nanmean(np.sin(rad)), np.nanmean(np.cos(rad))
    ))) % 360

    if 45 <= mean_angle < 135:
        return 'E'
    if 225 <= mean_angle < 315:
        return 'W'
    if mean_angle < 45 or mean_angle >= 315:
        return 'N'
    return 'S'


def estimate_heading_bias(
    df_all: pd.DataFrame,
    col: str = 'Mag1_IGRF',
) -> float:
    """
    Estimate the heading bias from all selected lines.

    Parameters
    ----------
    df_all : concatenated DataFrame of all selected line segments,
             must have columns: line_id, flight_id, Yaw, and col
    col    : magnetic column to use for DC-level estimation

    Returns
    -------
    bias : float
        Half the mean difference between E and W line DC levels (nT).
        Positive means E lines read higher than W lines.
    """
    if col not in df_all.columns or 'Yaw' not in df_all.columns:
        return 0.0

    means_e, means_w = [], []

    for (fid, lid), seg in df_all.groupby(['flight_id', 'line_id']):
        seg_valid = seg.dropna(subset=['Yaw', col])
        if len(seg_valid) < 10:
            continue
        direction = _classify_heading(seg_valid['Yaw'].values)
        line_mean = float(seg_valid[col].mean())
        if direction == 'E':
            means_e.append(line_mean)
        elif direction == 'W':
            means_w.append(line_mean)

    if not means_e or not means_w:
        print(f"  [HEADING] Not enough E/W lines to estimate bias — correction skipped.")
        return 0.0

    mu_e = float(np.mean(means_e))
    mu_w = float(np.mean(means_w))
    bias = (mu_e - mu_w) / 2.0

    print(f"  [HEADING] E lines ({len(means_e)}): mean = {mu_e:.3f} nT")
    print(f"  [HEADING] W lines ({len(means_w)}): mean = {mu_w:.3f} nT")
    print(f"  [HEADING] Bias (μ_E − μ_W) / 2 = {bias:+.3f} nT")

    return bias


def apply_heading(
    df: pd.DataFrame,
    bias: float,
) -> pd.DataFrame:
    """
    Apply the heading correction to one flight's DataFrame.

    Each sample is corrected based on the instantaneous Yaw:
        E heading → subtract bias
        W heading → add bias
        N/S       → no correction (tie lines or transitional headings)

    Parameters
    ----------
    df   : flight DataFrame with Yaw, Mag1_IGRF, Mag2_IGRF
    bias : heading bias in nT (from estimate_heading_bias)
    """
    df = df.copy()

    if 'Yaw' not in df.columns or bias == 0.0:
        for col in ('Mag1_IGRF', 'Mag2_IGRF'):
            if col in df.columns:
                df[col.replace('IGRF', 'IGRF_head')] = df[col]
        df['heading_bias_nT'] = 0.0
        return df

    yaw = df['Yaw'].values
    rad = np.radians(yaw % 360)
    mean_angle = np.degrees(np.arctan2(np.sin(rad), np.cos(rad))) % 360

    # Per-sample correction: sign follows heading
    is_east = (mean_angle >= 45) & (mean_angle < 135)
    is_west = (mean_angle >= 225) & (mean_angle < 315)

    correction = np.zeros(len(df))
    correction[is_east] = -bias
    correction[is_west] = +bias

    df['heading_bias_nT'] = correction

    for col in ('Mag1_IGRF', 'Mag2_IGRF'):
        if col in df.columns:
            out_col = col.replace('IGRF', 'IGRF_head')
            df[out_col] = df[col] + correction

    return df
