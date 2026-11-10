"""
Module 2 — Estimación y corrección del lag GPS-magnetómetro.

El magnetómetro de precesión de Larmor necesita completar un ciclo antes de
emitir cada valor (~0.3-0.5 s de latencia). El GPS no tiene esta latencia.
El resultado es que cada valor magnético queda asociado a la posición donde
el avión estaba lag_s segundos ANTES de la medición real.

Efecto visible: la misma anomalía geológica aparece desplazada en direcciones
opuestas al comparar líneas voladas en sentidos contrarios (E vs O).

A 200 km/h, 0.5 s de lag equivale a ~28 m de error posicional.

Funciones principales
---------------------
estimate_lag(df, config) → dict
    Estima el lag por cross-correlación entre pares de líneas opuestas.

apply_lag(df, lag_s) → DataFrame
    Aplica la corrección desplazando las columnas GPS en el tiempo.

plot_lag_diagnosis(seg_e, seg_o, lag_s, output_path)
    PNG de diagnóstico: perfiles antes y después de alinear.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

MAX_LAG_S     = 2.0      # ventana de búsqueda de la cross-correlación (un lag real es una fracción de segundo)
MIN_OVERLAP_M = 2000.0   # tramo común mínimo que debe tener un par de pasadas


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _cumulative_distance_m(df: pd.DataFrame) -> np.ndarray:
    """Distancia haversine acumulada (metros), asumiendo filas ya ordenadas por timestamp."""
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6_371_000.0 * np.sqrt(dlat**2 + (np.cos(lat_mid) * dlon)**2)
    return np.concatenate([[0.0], np.cumsum(d)])


def _velocidad_segmento_ms(seg: pd.DataFrame) -> float | None:
    """Velocidad mediana (m/s) de un solo segmento, a partir de posiciones GPS y M3clk."""
    seg = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps', 'M3clk'])
    if len(seg) < 2:
        return None
    lon = np.radians(seg['Xgps'].values)
    lat = np.radians(seg['Ygps'].values)
    dt_s = np.diff(seg['M3clk'].values) / 1000.0
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d_m = 6_371_000.0 * np.sqrt(dlat**2 + (np.cos(lat_mid) * dlon)**2)
    mask = dt_s > 0
    if not mask.any():
        return None
    return float(np.median(d_m[mask] / dt_s[mask]))


def _velocidad_media_ms(df: pd.DataFrame) -> float:
    """
    Velocidad media en m/s: mediana de las velocidades de cada segmento (flight_id, line_id).

    M3clk arranca de cero en cada vuelo, por eso las diferencias se calculan dentro de
    cada segmento. Ordenar filas de distintos vuelos por M3clk y diferenciarlas juntas
    mezcla posiciones lejanas con tiempos casi iguales y da velocidades absurdas.
    """
    if {'flight_id', 'line_id'}.issubset(df.columns):
        v = [_velocidad_segmento_ms(seg) for _, seg in df.groupby(['flight_id', 'line_id'])]
        v = [x for x in v if x is not None]
        return float(np.median(v)) if v else 50.0
    v = _velocidad_segmento_ms(df)
    return 50.0 if v is None else v


def _yaw_medio_circular(yaw: np.ndarray) -> float:
    """Media circular de ángulos en grados, resultado en [0, 360)."""
    rad = np.radians(yaw % 360)
    ang = float(np.degrees(np.arctan2(np.mean(np.sin(rad)), np.mean(np.cos(rad)))))
    return ang % 360


def _direccion_linea(yaw: np.ndarray) -> str:
    """
    Clasifica la dirección de vuelo de una línea a partir de su Yaw.
    Retorna 'E', 'O', 'N', 'S' o 'ND' (no determinado).
    """
    yaw_m = _yaw_medio_circular(yaw)
    if 45 <= yaw_m < 135:
        return 'E'
    if 225 <= yaw_m < 315:
        return 'O'
    if yaw_m < 45 or yaw_m >= 315:
        return 'N'
    return 'S'


def _con_campo_medio(seg: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega 'mag' = promedio de Mag1C y Mag2C y descarta filas sin posición o sin campo.

    Los magnetómetros están en las puntas de las alas (~10.56 m entre sí), a ambos lados
    del GPS. Su promedio queda sobre la traza del GPS y cancela el desfase lateral, que
    de otro modo se parecería a un corrimiento a lo largo de la línea (con signo opuesto
    en cada sensor).
    """
    cols = [c for c in ('Mag1C', 'Mag2C') if c in seg.columns]
    seg = seg.sort_values('M3clk').copy()
    seg['mag'] = seg[cols].mean(axis=1)
    return seg.dropna(subset=['Xgps', 'Ygps', 'mag'])


def _perfiles_alineados(seg_e: pd.DataFrame, seg_o: pd.DataFrame, paso_m: float):
    """
    Campo magnético (promedio de Mag1C y Mag2C) de dos pasadas sobre la MISMA grilla
    de coordenada Este (m), centrados en 0.

    Se alinea por coordenada absoluta y no por distancia desde el inicio de cada línea:
    cada pasada empieza en un punto distinto, y ese desfase se confundiría con lag.
    El orden temporal no importa: la pasada hacia el oeste queda también ordenada W→E.

    Retorna (p_e, p_o), o None si algún segmento tiene menos de 10 puntos o el tramo
    común es menor que MIN_OVERLAP_M.
    """
    segs = [_con_campo_medio(s) for s in (seg_e, seg_o)]
    if any(len(s) < 10 for s in segs):
        return None

    lat0 = np.radians(np.mean([s['Ygps'].mean() for s in segs]))   # misma latitud para ambas
    perfiles = []
    for s in segs:
        x = np.radians(s['Xgps'].values) * np.cos(lat0) * 6_371_000.0
        m = s['mag'].values
        orden = np.argsort(x)
        x, m = x[orden], m[orden]
        keep = np.concatenate([[True], np.diff(x) > 0])
        perfiles.append((x[keep], m[keep]))

    (xe, me), (xo, mo) = perfiles
    a, b = max(xe[0], xo[0]), min(xe[-1], xo[-1])
    if b - a < MIN_OVERLAP_M:
        return None

    grilla = np.arange(a, b, paso_m)
    p_e = np.interp(grilla, xe, me)
    p_o = np.interp(grilla, xo, mo)
    return p_e - p_e.mean(), p_o - p_o.mean()


def _offset_muestras(p_e: np.ndarray, p_o: np.ndarray, paso_m: float, vel_ms: float) -> int:
    """
    Corrimiento (en muestras de la grilla) que mejor alinea p_o con p_e, dentro de ±MAX_LAG_S.

    Convención de numpy: k > 0 significa que p_e queda k muestras a la derecha de p_o.
    """
    n = len(p_e)
    corr = np.correlate(p_e, p_o, mode='full')
    k = np.arange(-(n - 1), n)
    max_k = int(MAX_LAG_S * 2.0 * vel_ms / paso_m)
    ventana = np.abs(k) <= max_k
    return int(k[ventana][np.argmax(corr[ventana])])


def _estimar_lag_par(
    seg_e: pd.DataFrame,
    seg_o: pd.DataFrame,
    paso_m: float,
    vel_ms: float,
) -> float | None:
    """
    Estima el lag GPS-magnetómetro (segundos) para una misma línea volada en sentidos opuestos.

    Método: cross-correlación entre los perfiles de ambas pasadas, sobre la misma
    coordenada Este. La diferencia de posición de la misma anomalía entre los dos
    perfiles es 2 × lag_m (las pasadas se desplazan en sentidos opuestos por igual
    magnitud), por eso se divide el offset de la correlación por 2.

    Convención de signo (verificada con apply_lag: aplicar +lag_s reduce el desfase):
        lag_s > 0  →  GPS detrás del magnetómetro (caso típico)
        lag_s < 0  →  GPS adelantado (caso poco común)
    """
    perfiles = _perfiles_alineados(seg_e, seg_o, paso_m)
    if perfiles is None:
        return None

    k = _offset_muestras(perfiles[0], perfiles[1], paso_m, vel_ms)
    return float(k * paso_m / (2.0 * vel_ms)) if vel_ms > 0 else 0.0


def _identificar_pares(df: pd.DataFrame) -> list:
    """
    Identifica las líneas voladas dos veces en sentidos opuestos (mismo line_id, distinto vuelo).

    Es el único caso en que la misma traza se mide hacia el este y hacia el oeste, así
    que la diferencia de posición de una misma anomalía se debe solo al lag. Con líneas
    vecinas (un espaciado de línea) no sirve: el corrimiento entre ellas lo domina la geología.

    Retorna lista de tuplas (fila_e, fila_o), cada una es una Serie de pandas
    con columnas: flight_id, line_id, direccion.
    """
    registros = []
    for (fid, lid), seg in df.groupby(['flight_id', 'line_id']):
        seg_v = seg[seg['line_valid'] & seg['Yaw'].notna() & seg['Mag1C'].notna()]
        if len(seg_v) < 20:
            continue
        dir_linea = _direccion_linea(seg_v['Yaw'].values)
        if dir_linea not in ('E', 'O'):
            continue
        registros.append({'flight_id': fid, 'line_id': lid, 'direccion': dir_linea})

    if not registros:
        return []

    pares = []
    for _, grupo in pd.DataFrame(registros).groupby('line_id'):
        if 'E' in grupo['direccion'].values and 'O' in grupo['direccion'].values:
            pares.append((grupo[grupo['direccion'] == 'E'].iloc[0],
                          grupo[grupo['direccion'] == 'O'].iloc[0]))
    return pares


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def estimate_lag(df_all_lines: pd.DataFrame, config: dict) -> dict:
    """
    Estima el lag entre GPS y magnetómetro a partir de líneas paralelas opuestas.

    Algoritmo
    ---------
    Para cada línea volada en ambos sentidos (mismo line_id, una pasada E y otra O):
        1. Perfil de ambas pasadas (promedio de Mag1C y Mag2C) sobre la misma
           coordenada Este, sin nivel DC.
        2. Cross-correlación: el pico en offset k indica un desplazamiento
           total de 2 × lag_m entre los perfiles.
        3. lag_s = (k × paso_m) / (2 × velocidad_media).
    Reportar: mediana de los lags estimados por par.

    Las líneas vecinas no sirven como par: lo que las desplaza es la geología.
    Hay que pasar todas las pasadas disponibles, no solo las seleccionadas,
    porque las repeticiones son las que forman los pares.

    Criterio de decisión
    --------------------
    lag_tolerable = (line_spacing_m / 4) / velocidad_media
    |lag_mediano| < lag_tolerable  →  LAG_NEGLIGIBLE
    |lag_mediano| ≥ lag_tolerable  →  LAG_SIGNIFICANT

    Parámetros
    ----------
    df_all_lines : DataFrame con todas las líneas seleccionadas (todas las fechas/vuelos).
                   Columnas requeridas: flight_id, line_id, line_valid, Xgps, Ygps,
                   M3clk, Mag1C, Yaw.
    config       : diccionario leído de project.yaml.

    Retorna
    -------
    dict con claves: lag_median_s, lag_std_s, lag_tolerable_s, n_pairs,
                     decision, velocity_median_ms.
    """
    line_spacing_m = config['survey_design']['line_spacing_m']

    vel_ms = _velocidad_media_ms(df_all_lines)
    dt_nominal_s = 0.1  # ~10 Hz
    paso_m = vel_ms * dt_nominal_s

    print(f"[M2 LAG] Mean velocity       : {vel_ms:.1f} m/s")
    print(f"[M2 LAG] Spatial step        : {paso_m:.1f} m")

    pares = _identificar_pares(df_all_lines)
    print(f"[M2 LAG] E/W pairs found     : {len(pares)}")

    resultado_vacio = {
        'lag_median_s':      0.0,
        'lag_std_s':         0.0,
        'lag_tolerable_s':   (line_spacing_m / 4.0) / vel_ms,
        'n_pairs':           0,
        'decision':          'LAG_UNKNOWN',
        'velocity_median_ms': vel_ms,
    }

    if not pares:
        print("[M2 LAG] No pairs available for cross-correlation.")
        return resultado_vacio

    lags = []
    for fila_e, fila_o in pares:
        k_e = (fila_e['flight_id'], fila_e['line_id'])
        k_o = (fila_o['flight_id'], fila_o['line_id'])

        seg_e = df_all_lines[
            (df_all_lines['flight_id'] == k_e[0]) &
            (df_all_lines['line_id']   == k_e[1]) &
            df_all_lines['line_valid']
        ].copy()
        seg_o = df_all_lines[
            (df_all_lines['flight_id'] == k_o[0]) &
            (df_all_lines['line_id']   == k_o[1]) &
            df_all_lines['line_valid']
        ].copy()

        lag_s = _estimar_lag_par(seg_e, seg_o, paso_m, vel_ms)
        if lag_s is not None:
            lags.append(lag_s)
            print(f"[M2 LAG]   Line {k_e[1]}  E flight {k_e[0]} / W flight {k_o[0]}: lag = {lag_s:+.3f} s")

    if not lags:
        print("[M2 LAG] Cross-correlation returned no valid results.")
        return resultado_vacio

    lag_median     = float(np.median(lags))
    lag_std        = float(np.std(lags))
    lag_tolerable  = (line_spacing_m / 4.0) / vel_ms
    decision       = 'LAG_SIGNIFICANT' if abs(lag_median) >= lag_tolerable else 'LAG_NEGLIGIBLE'

    sep = '─' * 50
    print(f"\n[M2 LAG] {sep}")
    print(f"[M2 LAG] Median lag    : {lag_median:+.3f} s")
    print(f"[M2 LAG] Lag std       : {lag_std:.3f} s")
    print(f"[M2 LAG] Lag tolerance : {lag_tolerable:.3f} s  (= spacing/4 / v)")
    print(f"[M2 LAG] Pairs used    : {len(lags)}")
    print(f"[M2 LAG] Decision      : {decision}")
    print(f"[M2 LAG] {sep}\n")

    return {
        'lag_median_s':       lag_median,
        'lag_std_s':          lag_std,
        'lag_tolerable_s':    lag_tolerable,
        'n_pairs':            len(lags),
        'decision':           decision,
        'velocity_median_ms': vel_ms,
    }


def apply_lag(df: pd.DataFrame, lag_s: float) -> pd.DataFrame:
    """
    Aplica la corrección de lag desplazando las posiciones GPS en el tiempo.

    Para lag_s > 0 (GPS registra posición anterior a la real), la corrección
    asigna a cada muestra magnética la posición GPS que llega lag_samples
    instantes más tarde, acercando la posición registrada a la posición real.

    El DataFrame debe corresponder a un único vuelo y estar ordenado por M3clk.
    Solo llamar si estimate_lag devuelve LAG_SIGNIFICANT.

    Parámetros
    ----------
    df    : DataFrame de un vuelo con columnas Xgps, Ygps, Zgps, M3clk, line_valid.
    lag_s : lag en segundos (positivo = GPS detrás del magnetómetro).

    Retorna
    -------
    DataFrame con posiciones GPS corregidas y columna 'lag_applied' = True.
    Los extremos afectados quedan marcados como line_valid = False.
    """
    df = df.copy().sort_values('M3clk').reset_index(drop=True)

    dt_medio_s = df['M3clk'].diff().median() / 1000.0
    if not np.isfinite(dt_medio_s) or dt_medio_s <= 0:
        print("[M2 LAG] Could not compute dt_medio. Correction not applied.")
        df['lag_applied'] = False
        return df

    lag_samples = int(round(lag_s / dt_medio_s))

    print(f"[M2 LAG] Correction: lag = {lag_s:.3f} s  →  {lag_samples} samples  "
          f"(dt = {dt_medio_s * 1000:.1f} ms)")

    if lag_samples == 0:
        print("[M2 LAG] lag_samples = 0, no correction needed.")
        df['lag_applied'] = True
        return df

    n = len(df)
    col_gps = [c for c in ('Xgps', 'Ygps', 'Zgps') if c in df.columns]

    for col in col_gps:
        vals   = df[col].values.astype(float).copy()
        nuevos = np.full(n, np.nan)
        if lag_samples > 0:
            # Avanzar GPS: para el instante i usar la posición de i+lag_samples
            nuevos[:n - lag_samples] = vals[lag_samples:]
        else:
            ls = abs(lag_samples)
            nuevos[ls:] = vals[:n - ls]
        df[col] = nuevos

    # Marcar extremos sin posición GPS válida como inválidos
    n_inv = abs(lag_samples)
    if lag_samples > 0:
        df.loc[df.index[n - n_inv:], 'line_valid'] = False
    else:
        df.loc[df.index[:n_inv], 'line_valid'] = False

    df['lag_applied'] = True
    print(f"[M2 LAG] GPS columns adjusted    : {col_gps}")
    print(f"[M2 LAG] Samples marked NaN      : {n_inv}")
    return df


def lag_effect(df: pd.DataFrame, lag_s: float,
               cols: tuple[str, ...] = ('Mag1C', 'Mag2C')) -> tuple[pd.DataFrame, int]:
    """
    Cambio que produciría apply_lag en el valor magnético de cada punto (después − antes).

    apply_lag asigna a la muestra i la posición de la muestra i+k, así que en la posición
    original j el valor pasa a ser el de la muestra j−k. No modifica df.

    Retorna (efecto, k): las filas de df ordenadas por M3clk, con sus posiciones originales
    y una columna 'd_<col>' por columna magnética (nT), y el desplazamiento k en muestras.
    """
    df = df.sort_values('M3clk').reset_index(drop=True)
    dt_s = df['M3clk'].diff().median() / 1000.0
    k = int(round(lag_s / dt_s)) if np.isfinite(dt_s) and dt_s > 0 else 0
    out = df[['flight_id', 'line_id', 'line_valid', 'Xgps', 'Ygps']].copy()
    for c in cols:
        out[f'd_{c}'] = df[c].shift(k) - df[c]
    return out, k


def plot_lag_diagnosis(
    seg_e: pd.DataFrame,
    seg_o: pd.DataFrame,
    lag_s: float,
    output_path: Path,
    paso_m: float = 5.0,
) -> None:
    """
    PNG de diagnóstico de lag para un par de líneas E/O.

    Panel 1 — Antes de corrección: ambos perfiles W→E superpuestos.
              El desplazamiento entre anomalías es el efecto del lag.
    Panel 2 — Después de corrección: perfil O alineado al E por el offset
              de la cross-correlación, verificando que las anomalías coincidan.

    Parámetros
    ----------
    seg_e       : segmento de la línea volada hacia el este
    seg_o       : segmento de la línea volada hacia el oeste
    lag_s       : lag estimado en segundos (de estimate_lag)
    output_path : ruta de salida del PNG
    paso_m      : paso de la grilla espacial (m)
    """
    vel_ms = _velocidad_media_ms(pd.concat([seg_e, seg_o], ignore_index=True))

    perfiles = _perfiles_alineados(seg_e, seg_o, paso_m)
    if perfiles is None:
        print("[M2 LAG] Not enough data for diagnosis.")
        return
    p_e, p_o = perfiles
    n = len(p_e)

    # Offset de la cross-correlación (en muestras del perfil espacial)
    lag_peak_samples = _offset_muestras(p_e, p_o, paso_m, vel_ms)

    lid_e = int(seg_e['line_id'].iloc[0])
    lid_o = int(seg_o['line_id'].iloc[0])
    dist  = np.arange(n) * paso_m

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle(
        f"Lag diagnosis  |  Line {lid_e} (E→) vs Line {lid_o} (←W)  "
        f"|  lag = {lag_s:+.3f} s",
        fontsize=12,
    )

    # --- Panel 1: before correction ---
    ax = axes[0]
    ax.set_title("Before correction (visible offset between anomalies)")
    ax.plot(dist, p_e, color='steelblue',  linewidth=0.9, label=f'Line {lid_e} (E→)')
    ax.plot(dist, p_o, color='darkorange', linewidth=0.9, label=f'Line {lid_o} (←W)')
    ax.set_ylabel('Mean of Mag1C and Mag2C (nT, centered)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    desplaz_m = abs(lag_peak_samples) * paso_m
    ax.annotate(
        f'Observed offset ≈ {desplaz_m:.0f} m ({lag_peak_samples} samples)',
        xy=(0.02, 0.97), xycoords='axes fraction', va='top', fontsize=8,
    )

    # --- Panel 2: after correction (aligned via correlation shift) ---
    ax = axes[1]
    ax.set_title("After correction (W profile aligned to E)")

    ls = lag_peak_samples
    if ls > 0:
        # p_e queda ls muestras a la derecha de p_o → desplazar p_o hacia la derecha
        p_o_alin = np.empty(n)
        p_o_alin[:ls] = np.nan
        p_o_alin[ls:] = p_o[:n - ls]
    elif ls < 0:
        ls_abs = abs(ls)
        p_o_alin = np.empty(n)
        p_o_alin[:n - ls_abs] = p_o[ls_abs:]
        p_o_alin[n - ls_abs:] = np.nan
    else:
        p_o_alin = p_o.copy()

    ax.plot(dist, p_e,      color='steelblue',  linewidth=0.9, label=f'Line {lid_e} (E→)')
    ax.plot(dist, p_o_alin, color='darkorange', linewidth=0.9, label=f'Line {lid_o} (aligned)')
    ax.set_ylabel('Mean of Mag1C and Mag2C (nT, centered)')
    ax.set_xlabel('Distance along the common track (m)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  [M2 LAG] Diagnosis saved: {output_path}")
