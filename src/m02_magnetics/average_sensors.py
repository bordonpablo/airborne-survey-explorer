"""
Module 2 — Step 6: Sensor average.

At this point in the chain both magnetometers have been independently corrected
for aircraft interference (compensation), diurnal variation, IGRF, and heading.
Combining them reduces random sensor noise by ~√2 (assuming uncorrelated noise).

Method
------
For each flight:
    1. Compute the high-frequency noise of Mag1_IGRF_head and Mag2_IGRF_head
       using the fourth-difference operator (standard geophysical noise estimator):
           noise = std( Δ⁴B ) / sqrt(70)
       where Δ⁴B[i] = B[i-2] - 4B[i-1] + 6B[i] - 4B[i+1] + B[i+2]
    2. If noise(Mag2) > 2 × noise(Mag1): use Mag1 only.
       If noise(Mag1) > 2 × noise(Mag2): use Mag2 only.
       Otherwise: simple average of both.
    3. Result stored in column Mag_IGRF_head.

The fourth-difference operator suppresses the geological signal (long-wavelength)
and isolates the sensor noise (short-wavelength), making it a robust noise estimator
even over magnetically active geology.

Adds columns
------------
    Mag_IGRF_head   : combined field after averaging / sensor selection (nT)
    sensor_used     : 'avg', 'Mag1', or 'Mag2' — which sensors contributed
"""

import numpy as np
import pandas as pd


def _fourth_difference_noise(x: np.ndarray) -> float:
    """
    Estimate sensor noise via the fourth-difference operator.

    Fourth difference: Δ⁴B[i] = B[i-2] - 4B[i-1] + 6B[i] - 4B[i+1] + B[i+2]
    Noise estimate   : std(Δ⁴B) / sqrt(70)

    The √70 normalisation converts the std of the fourth-difference sequence
    back to the equivalent std of the original noise process.
    """
    x = np.asarray(x, dtype=float)
    if len(x) < 5:
        return np.nan
    d4 = x[4:] - 4*x[3:-1] + 6*x[2:-2] - 4*x[1:-3] + x[:-4]
    return float(np.nanstd(d4) / np.sqrt(70))


def apply_sensor_average(
    df: pd.DataFrame,
    noise_ratio_threshold: float = 2.0,
) -> pd.DataFrame:
    """
    Combine Mag1_IGRF_head and Mag2_IGRF_head into Mag_IGRF_head.

    Parameters
    ----------
    df                    : flight DataFrame with Mag1_IGRF_head, Mag2_IGRF_head
    noise_ratio_threshold : if one sensor's noise exceeds this multiple of the
                            other's, the noisier sensor is discarded (default 2.0)

    Returns
    -------
    DataFrame with new columns Mag_IGRF_head and sensor_used.
    """
    df = df.copy()

    col1 = 'Mag1_IGRF_head'
    col2 = 'Mag2_IGRF_head'

    has1 = col1 in df.columns and df[col1].notna().any()
    has2 = col2 in df.columns and df[col2].notna().any()

    if not has1 and not has2:
        print("  [AVG] Neither Mag1_IGRF_head nor Mag2_IGRF_head found — skipping.")
        return df

    if has1 and has2:
        noise1 = _fourth_difference_noise(df[col1].dropna().values)
        noise2 = _fourth_difference_noise(df[col2].dropna().values)

        print(f"  [AVG] Noise Mag1_IGRF_head: {noise1:.4f} nT")
        print(f"  [AVG] Noise Mag2_IGRF_head: {noise2:.4f} nT")

        if np.isfinite(noise1) and np.isfinite(noise2):
            if noise2 > noise_ratio_threshold * noise1:
                df['Mag_IGRF_head'] = df[col1]
                df['sensor_used']   = 'Mag1'
                print(f"  [AVG] Mag2 noise {noise2/noise1:.1f}× Mag1 — using Mag1 only")
            elif noise1 > noise_ratio_threshold * noise2:
                df['Mag_IGRF_head'] = df[col2]
                df['sensor_used']   = 'Mag2'
                print(f"  [AVG] Mag1 noise {noise1/noise2:.1f}× Mag2 — using Mag2 only")
            else:
                df['Mag_IGRF_head'] = (df[col1] + df[col2]) / 2.0
                df['sensor_used']   = 'avg'
                print(f"  [AVG] Noise ratio within threshold — averaging both sensors")
        else:
            df['Mag_IGRF_head'] = (df[col1] + df[col2]) / 2.0
            df['sensor_used']   = 'avg'
    elif has1:
        df['Mag_IGRF_head'] = df[col1]
        df['sensor_used']   = 'Mag1'
        print("  [AVG] Only Mag1_IGRF_head available — using Mag1")
    else:
        df['Mag_IGRF_head'] = df[col2]
        df['sensor_used']   = 'Mag2'
        print("  [AVG] Only Mag2_IGRF_head available — using Mag2")

    return df
