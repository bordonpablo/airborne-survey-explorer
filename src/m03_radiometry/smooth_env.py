"""
Smooth environmental sensor channels before GammAn import.

GammAn's FSA uses Sralt, Sbaro, and Stemp at each second to apply the height
and HSTP corrections. Noise in those channels propagates directly into the
corrected ground concentrations. This smoothing removes high-frequency noise
while preserving real atmospheric and terrain-following trends.

Rolling median is used instead of mean: it is robust against isolated spike
values (e.g. radar altimeter glitches from terrain returns).
"""

import pandas as pd


def smooth_env(
    df: pd.DataFrame,
    window_sralt: int = 5,
    window_env: int = 5,
) -> pd.DataFrame:
    """
    Apply rolling-median smoothing to Sralt, Sbaro, and Stemp.

    Adds Sralt_smooth, Sbaro_smooth, Stemp_smooth to the DataFrame.
    Original columns are not modified.

    Parameters
    ----------
    window_sralt : smoothing window for Sralt in samples (1 sample = 1 s)
    window_env   : smoothing window for Sbaro and Stemp

    Returns
    -------
    Copy of df with three added columns.
    """
    out = df.copy()

    for col, window in [
        ('Sralt', window_sralt),
        ('Sbaro', window_env),
        ('Stemp', window_env),
    ]:
        out[f'{col}_smooth'] = (
            df[col]
            .rolling(window=window, center=True, min_periods=1)
            .median()
        )

    return out
