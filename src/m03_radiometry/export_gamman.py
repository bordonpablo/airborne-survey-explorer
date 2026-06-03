"""
Generate GammAn-ready CSV files from SPC data (Etapa A).

Creates two CSV files per flight:

  SPC_decoded.csv       — referencia:
      Todas las columnas escalares del SPC + Sa2 + espectro decodificado
      (ch000…ch255). Sralt, Sbaro y Stemp con sus valores originales.

  SPC_gamman_ready.csv  — para importar en GammAn:
      Idéntico al anterior pero con Sralt, Sbaro y Stemp reemplazados
      por sus versiones suavizadas (rolling median).

Ambos archivos contienen el vuelo completo (no filtrado a líneas de
producción) porque GammAn necesita todos los espectros para la
estabilización espectral.

Notas sobre el espectro:
  El campo Sbin del SPC contiene 256 canales uint16 little-endian
  (1024 hex chars antes del terminador ffffffffff). Cada canal es un
  contador de fotones detectados en ese rango de energía. Se decodifican
  en columnas ch000…ch255.
"""

from pathlib import Path

import pandas as pd

from src.m03_radiometry.read_spc import read_spc
from src.m03_radiometry.smooth_env import smooth_env

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
    spc_path:     Path | str,
    out_dir:      Path | str,
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
    (gamman_path, decoded_path)
    """
    spc_path = Path(spc_path)
    out_dir  = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = read_spc(spc_path, decode_spectrum=True)
    if df.empty:
        raise ValueError(f'No data parsed from {spc_path.name}')

    df_smooth = smooth_env(df, window_sralt, window_env)

    # Only keep columns that exist (Sa2 present when decode_spectrum=True)
    cols = [c for c in _SCALAR_COLS + _CHANNEL_COLS if c in df.columns]

    def _clean(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        if 'Swayp' in out.columns:
            out['Swayp'] = out['Swayp'].fillna('0').replace('', '0')
        return out

    # ── SPC_decoded.csv — valores originales ─────────────────────────────────
    decoded_path = out_dir / 'SPC_decoded.csv'
    _clean(df[cols]).to_csv(decoded_path, index=False)

    # ── SPC_gamman_ready.csv — Sralt/Sbaro/Stemp suavizados ──────────────────
    df_out = df[cols].copy()
    df_out['Sralt'] = df_smooth['Sralt_smooth'].values
    df_out['Sbaro'] = df_smooth['Sbaro_smooth'].values
    df_out['Stemp'] = df_smooth['Stemp_smooth'].values

    gamman_path = out_dir / 'SPC_gamman_ready.csv'
    _clean(df_out).to_csv(gamman_path, index=False)

    return gamman_path, decoded_path
