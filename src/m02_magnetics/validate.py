"""
Module 2 — Validación contra datos procesados por el especialista.

Permite comparar columnas propias con los datos de referencia entregados
por el geofísico responsable de la campaña (formato Geosoft / Oasis Montaj).

Formato esperado:
    .ddf — definición de columnas (nombre, tipo, byte_start, byte_end)
    .dat — datos en ASCII de ancho fijo

Uso desde run.py o independientemente:
    from src.m02_magnetics.validate import read_specialist_data, compare_columns
"""

from pathlib import Path

import numpy as np
import pandas as pd


def _parsear_ddf(path_ddf: Path) -> list[dict]:
    """
    Extrae nombre, dtype, byte_start y byte_end de cada columna del .ddf.

    Formato esperado por línea (separado por comas o tabuladores):
        NOMBRE, TIPO, BYTE_START, BYTE_END
    Las líneas que comienzan con '/' son comentarios y se ignoran.
    """
    columnas = []
    with open(path_ddf, 'r', encoding='latin-1') as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith('/'):
                continue
            partes = [p.strip() for p in linea.replace(',', '\t').split('\t') if p.strip()]
            if len(partes) < 4:
                continue
            try:
                columnas.append({
                    'nombre':     partes[0],
                    'dtype':      partes[1],
                    'byte_start': int(partes[2]),
                    'byte_end':   int(partes[3]),
                })
            except (ValueError, IndexError):
                continue
    return columnas


def read_specialist_data(path_dat: str | Path, path_ddf: str | Path) -> pd.DataFrame:
    """
    Lee un par de archivos .dat/.ddf del especialista (formato Geosoft/Oasis Montaj).

    El archivo .ddf describe las columnas con nombre, tipo de dato y rango de bytes.
    El archivo .dat contiene los datos en ASCII de ancho fijo.

    Parámetros
    ----------
    path_dat : ruta al archivo .dat con los datos
    path_ddf : ruta al archivo .ddf con la definición de columnas

    Retorna
    -------
    DataFrame con columnas nombradas según el .ddf, indexado por fid (si existe).
    """
    path_dat = Path(path_dat)
    path_ddf = Path(path_ddf)

    if not path_dat.exists():
        raise FileNotFoundError(f"Archivo .dat no encontrado: {path_dat}")
    if not path_ddf.exists():
        raise FileNotFoundError(f"Archivo .ddf no encontrado: {path_ddf}")

    print(f"[M2 VALIDATE] Leyendo definición de columnas: {path_ddf.name}")
    columnas = _parsear_ddf(path_ddf)

    if not columnas:
        raise ValueError(f"No se encontraron columnas válidas en {path_ddf}")

    nombres   = [c['nombre']     for c in columnas]
    col_specs = [(c['byte_start'], c['byte_end']) for c in columnas]

    print(f"[M2 VALIDATE] Columnas encontradas: {nombres}")
    print(f"[M2 VALIDATE] Leyendo datos: {path_dat.name}")

    df = pd.read_fwf(
        path_dat,
        colspecs=col_specs,
        names=nombres,
        comment='/',
    )

    # Convertir a numérico según tipo declarado en .ddf
    for col_info in columnas:
        nombre = col_info['nombre']
        if nombre not in df.columns:
            continue
        dtype = col_info.get('dtype', 'float').lower()
        if 'int' in dtype:
            df[nombre] = pd.to_numeric(df[nombre], errors='coerce').astype('Int64')
        else:
            df[nombre] = pd.to_numeric(df[nombre], errors='coerce')

    # Usar fid como índice si existe
    for col_fid in ('fid', 'FID', 'Fid'):
        if col_fid in df.columns:
            df = df.rename(columns={col_fid: 'fid'}).set_index('fid')
            break

    print(f"[M2 VALIDATE] Filas leídas: {len(df):,}  |  Columnas: {len(df.columns)}")
    return df


def compare_columns(
    df_ours: pd.DataFrame,
    col_ours: str,
    df_ref: pd.DataFrame,
    col_ref: str,
    label: str,
) -> dict:
    """
    Compara una columna propia con la referencia del especialista.

    Alinea los datos por índice compartido (fid o timestamp), calcula estadísticas
    de diferencia y reporta el resultado en terminal.

    Parámetros
    ----------
    df_ours  : DataFrame con los datos procesados por nosotros
    col_ours : nombre de la columna a comparar en df_ours
    df_ref   : DataFrame de referencia (datos del especialista)
    col_ref  : nombre de la columna equivalente en df_ref
    label    : etiqueta descriptiva para el reporte (ej. 'Mag1C corr. diurna')

    Retorna
    -------
    dict con claves: mean_diff, std_diff, max_abs_diff, rmse, n_points
    """
    if col_ours not in df_ours.columns:
        raise KeyError(f"Columna '{col_ours}' no encontrada en df_ours.")
    if col_ref not in df_ref.columns:
        raise KeyError(f"Columna '{col_ref}' no encontrada en df_ref.")

    idx_comun = df_ours.index.intersection(df_ref.index)
    if len(idx_comun) == 0:
        print(f"[M2 VALIDATE] {label}: sin índices en común, no se puede comparar.")
        return {
            'mean_diff': np.nan, 'std_diff': np.nan,
            'max_abs_diff': np.nan, 'rmse': np.nan, 'n_points': 0,
        }

    a = pd.to_numeric(df_ours.loc[idx_comun, col_ours], errors='coerce')
    b = pd.to_numeric(df_ref.loc[idx_comun, col_ref],   errors='coerce')
    diff = (a - b).dropna()
    n = len(diff)

    if n == 0:
        print(f"[M2 VALIDATE] {label}: todos los valores son NaN tras alinear.")
        return {
            'mean_diff': np.nan, 'std_diff': np.nan,
            'max_abs_diff': np.nan, 'rmse': np.nan, 'n_points': 0,
        }

    mean_diff    = float(diff.mean())
    std_diff     = float(diff.std())
    max_abs_diff = float(diff.abs().max())
    rmse         = float(np.sqrt((diff**2).mean()))

    sep = '─' * 55
    print(f"\n[M2 VALIDATE] {sep}")
    print(f"[M2 VALIDATE] Comparación : {label}")
    print(f"[M2 VALIDATE]   Nuestro   : {col_ours}")
    print(f"[M2 VALIDATE]   Referencia: {col_ref}")
    print(f"[M2 VALIDATE]   Puntos alineados : {n:,}")
    print(f"[M2 VALIDATE]   Diferencia media : {mean_diff:+.3f} nT")
    print(f"[M2 VALIDATE]   Desv. estándar   : {std_diff:.3f} nT")
    print(f"[M2 VALIDATE]   Máx |diferencia| : {max_abs_diff:.3f} nT")
    print(f"[M2 VALIDATE]   RMSE             : {rmse:.3f} nT")
    print(f"[M2 VALIDATE] {sep}\n")

    return {
        'mean_diff':    mean_diff,
        'std_diff':     std_diff,
        'max_abs_diff': max_abs_diff,
        'rmse':         rmse,
        'n_points':     n,
    }
