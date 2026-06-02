"""
Generate GammAn-ready CSV files from SPC data (Etapa A).

Creates two CSV files per flight:

  SPC_gamman_ready.csv  — for GammAn import:
      All scalar SPC columns + Sa2 + decoded spectrum (ch000 … ch255),
      with Sralt, Sbaro and Stemp replaced by their smoothed values.

  SPC_decoded.csv  — reference version:
      Identical structure but Sralt, Sbaro and Stemp at original values.

Both files contain the full flight (not filtered to survey lines) because
GammAn needs all spectra for the spectral stabilisation step.
"""

from pathlib import Path

import pandas as pd

from src.m03_radiometry.read_spc import read_spc
from src.m03_radiometry.smooth_env import smooth_env


# Scalar columns in output order (spectrum channels are appended after)
_SCALAR_COLS = [
    'flight_id',
    'M2clk', 'Sdate', 'Stime', 'Swayp',
    'Sxgps', 'Sygps', 'Szgps',
    'Sralt', 'Sbaro', 'Stemp', 'Shumd',
    'Sreal', 'Slive', 'Srate',
    'Sk', 'Su', 'Sth',
    'Sa0', 'Sa1', 'Sa2',
]
_CHANNEL_COLS = [f'ch{i:03d}' for i in range(256)]


def export_gamman(
    spc_path:    Path | str,
    out_dir:     Path | str,
    window_sralt: int = 5,
    window_env:   int = 5,
) -> tuple[Path, Path]:
    """
    Generate SPC_gamman_ready.csv and SPC_decoded.csv for one flight.

    Parameters
    ----------
    spc_path      : path to the original SPC*.txt file
    out_dir       : output directory (created if it does not exist)
    window_sralt  : rolling-median window for Sralt  (samples = seconds)
    window_env    : rolling-median window for Sbaro and Stemp

    Returns
    -------
    (gamman_path, decoded_path) — paths to the two CSV files written.
    """
    spc_path = Path(spc_path)
    out_dir  = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = read_spc(spc_path, decode_spectrum=True)
    if df.empty:
        raise ValueError(f'No data parsed from {spc_path.name}')

    df_smooth = smooth_env(df, window_sralt, window_env)

    # Keep only columns that actually exist in df (Sa2 / channels may be
    # absent if spectrum decoding failed for all rows)
    cols = [c for c in _SCALAR_COLS + _CHANNEL_COLS if c in df.columns]

    # ── SPC_decoded.csv — original Sralt / Sbaro / Stemp ─────────────────────
    decoded_path = out_dir / 'SPC_decoded.csv'
    df[cols].to_csv(decoded_path, index=False)

    # ── SPC_gamman_ready.csv — smoothed Sralt / Sbaro / Stemp ────────────────
    df_out = df[cols].copy()
    df_out['Sralt'] = df_smooth['Sralt_smooth'].values
    df_out['Sbaro'] = df_smooth['Sbaro_smooth'].values
    df_out['Stemp'] = df_smooth['Stemp_smooth'].values

    gamman_path = out_dir / 'SPC_gamman_ready.csv'
    df_out.to_csv(gamman_path, index=False)

    return gamman_path, decoded_path
