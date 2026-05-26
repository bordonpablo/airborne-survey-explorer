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


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _distancia_acumulada_m(df: pd.DataFrame) -> np.ndarray:
    """Distancia haversine acumulada (metros), asumiendo filas ya ordenadas por timestamp."""
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6_371_000.0 * np.sqrt(dlat**2 + (np.cos(lat_mid) * dlon)**2)
    return np.concatenate([[0.0], np.cumsum(d)])


def _velocidad_media_ms(df: pd.DataFrame) -> float:
    """Velocidad media en m/s calculada a partir de posiciones GPS y M3clk."""
    seg = df.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps', 'M3clk'])
    if len(seg) < 2:
        return 50.0
    lon = np.radians(seg['Xgps'].values)
    lat = np.radians(seg['Ygps'].values)
    dt_s = np.diff(seg['M3clk'].values) / 1000.0
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d_m = 6_371_000.0 * np.sqrt(dlat**2 + (np.cos(lat_mid) * dlon)**2)
    mask = dt_s > 0
    if not mask.any():
        return 50.0
    return float(np.median(d_m[mask] / dt_s[mask]))


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


def _perfil_weste_este(seg: pd.DataFrame, paso_m: float) -> np.ndarray | None:
    """
    Interpola Mag1C a una grilla espacial regular orientada de oeste a este.

    Para líneas voladas en dirección O (hacia el oeste), invierte el orden
    temporal para que el perfil vaya siempre W→E en el espacio.
    Resta la media para eliminar el nivel DC (paso necesario antes de correlacionar).

    Retorna None si el segmento tiene menos de 10 puntos válidos.
    """
    seg = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps', 'Mag1C'])
    if len(seg) < 10:
        return None

    dist = _distancia_acumulada_m(seg)
    mag  = seg['Mag1C'].values.copy()

    # Si la línea va de E→O, invertir para obtener perfil W→E
    if seg['Xgps'].iloc[-1] < seg['Xgps'].iloc[0]:
        dist = dist[-1] - dist[::-1]
        mag  = mag[::-1]

    d_max    = dist[-1]
    d_regular = np.arange(0, d_max, paso_m)
    if len(d_regular) < 20:
        return None

    perfil = np.interp(d_regular, dist, mag)
    return perfil - perfil.mean()


def _estimar_lag_par(
    seg_e: pd.DataFrame,
    seg_o: pd.DataFrame,
    paso_m: float,
    vel_ms: float,
) -> float | None:
    """
    Estima el lag GPS-magnetómetro (segundos) para un par de líneas opuestas.

    Método: cross-correlación normalizada entre los perfiles W→E de ambas líneas.
    La diferencia de posición de la misma anomalía entre los dos perfiles es
    2 × lag_m (ambas líneas se desplazan en sentidos opuestos por igual magnitud),
    por eso se divide el offset de la correlación por 2.

    Convención de signo:
        lag_s > 0  →  GPS detrás del magnetómetro (caso típico)
        lag_s < 0  →  GPS adelantado (caso poco común)
    """
    p_e = _perfil_weste_este(seg_e, paso_m)
    p_o = _perfil_weste_este(seg_o, paso_m)

    if p_e is None or p_o is None:
        return None

    n = min(len(p_e), len(p_o))
    if n < 20:
        return None

    p_e = p_e[:n]
    p_o = p_o[:n]

    # Cross-correlación: c[k] tiene pico en k donde p_o[i-lag] ≈ p_e[i]
    # lag = k - (n-1).  Positivo → p_o está a la derecha de p_e.
    corr      = np.correlate(p_e, p_o, mode='full')
    lags_idx  = np.arange(-(n - 1), n)
    lag_samples = int(lags_idx[np.argmax(corr)])

    # El desplazamiento observable = 2 × lag_m → dividir por 2
    lag_m = abs(lag_samples) * paso_m / 2.0
    lag_s = lag_m / vel_ms if vel_ms > 0 else 0.0

    return float(np.sign(lag_samples) * lag_s)


def _identificar_pares(df: pd.DataFrame, line_spacing_m: float) -> list:
    """
    Identifica pares de líneas paralelas E/O para la estimación del lag.

    Prioridad 1: mismo line_id, distinto flight_id, dirección opuesta.
                 Ocurre cuando una línea fue re-volada en sentido contrario.
    Prioridad 2: líneas adyacentes (patrón lawnmower E-O-E-O), enlazadas
                 por la mínima diferencia de latitud media.

    Retorna lista de tuplas (fila_e, fila_o), cada una es una Serie de pandas
    con columnas: flight_id, line_id, direccion, lat_med.
    """
    registros = []
    for (fid, lid), seg in df.groupby(['flight_id', 'line_id']):
        seg_v = seg[seg['line_valid'] & seg['Yaw'].notna() & seg['Mag1C'].notna()]
        if len(seg_v) < 20:
            continue
        dir_linea = _direccion_linea(seg_v['Yaw'].values)
        if dir_linea not in ('E', 'O'):
            continue
        registros.append({
            'flight_id': fid,
            'line_id':   lid,
            'direccion': dir_linea,
            'lat_med':   float(seg_v['Ygps'].median()),
        })

    if not registros:
        return []

    segs = pd.DataFrame(registros)
    usados: set[tuple] = set()
    pares = []

    # Prioridad 1: mismo line_id, flight_id distinto, dirección opuesta
    for lid in segs['line_id'].unique():
        grupo = segs[segs['line_id'] == lid]
        if 'E' not in grupo['direccion'].values or 'O' not in grupo['direccion'].values:
            continue
        fila_e = grupo[grupo['direccion'] == 'E'].iloc[0]
        fila_o = grupo[grupo['direccion'] == 'O'].iloc[0]
        k_e = (fila_e['flight_id'], fila_e['line_id'])
        k_o = (fila_o['flight_id'], fila_o['line_id'])
        if k_e not in usados and k_o not in usados:
            pares.append((fila_e, fila_o))
            usados.add(k_e)
            usados.add(k_o)

    # Prioridad 2: pares adyacentes por latitud (patrón lawnmower)
    espaciado_deg = line_spacing_m / 111_000.0
    lineas_e = segs[segs['direccion'] == 'E'].copy()
    lineas_o = segs[segs['direccion'] == 'O'].copy()

    for _, fila_e in lineas_e.iterrows():
        k_e = (fila_e['flight_id'], fila_e['line_id'])
        if k_e in usados:
            continue

        disponibles_o = lineas_o[
            ~lineas_o.apply(lambda r: (r['flight_id'], r['line_id']) in usados, axis=1)
        ]
        if disponibles_o.empty:
            break

        dists_lat = (disponibles_o['lat_med'] - fila_e['lat_med']).abs()
        idx_min   = dists_lat.idxmin()

        if dists_lat[idx_min] <= 1.5 * espaciado_deg:
            fila_o = disponibles_o.loc[idx_min]
            k_o    = (fila_o['flight_id'], fila_o['line_id'])
            pares.append((fila_e, fila_o))
            usados.add(k_e)
            usados.add(k_o)

    return pares


# ---------------------------------------------------------------------------
# Funciones públicas
# ---------------------------------------------------------------------------

def estimate_lag(df_all_lines: pd.DataFrame, config: dict) -> dict:
    """
    Estima el lag entre GPS y magnetómetro a partir de líneas paralelas opuestas.

    Algoritmo
    ---------
    Para cada par de líneas E/O:
        1. Extraer perfil Mag1C vs distancia acumulada (W→E para ambas).
        2. Restar la media de línea (eliminar nivel DC).
        3. Cross-correlación: el pico en offset k indica un desplazamiento
           total de 2 × lag_m entre los perfiles.
        4. lag_s = (k × paso_m) / (2 × velocidad_media).
    Reportar: mediana de los lags estimados por par.

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

    print(f"[M2 LAG] Velocidad media     : {vel_ms:.1f} m/s")
    print(f"[M2 LAG] Paso espacial       : {paso_m:.1f} m")

    pares = _identificar_pares(df_all_lines, line_spacing_m)
    print(f"[M2 LAG] Pares E/O encontrados: {len(pares)}")

    resultado_vacio = {
        'lag_median_s':      0.0,
        'lag_std_s':         0.0,
        'lag_tolerable_s':   (line_spacing_m / 4.0) / vel_ms,
        'n_pairs':           0,
        'decision':          'LAG_UNKNOWN',
        'velocity_median_ms': vel_ms,
    }

    if not pares:
        print("[M2 LAG] Sin pares disponibles para cross-correlación.")
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
            print(f"[M2 LAG]   Par línea {k_e[1]} (E) vs {k_o[1]} (O): lag = {lag_s:+.3f} s")

    if not lags:
        print("[M2 LAG] Cross-correlación sin resultados válidos.")
        return resultado_vacio

    lag_median     = float(np.median(lags))
    lag_std        = float(np.std(lags))
    lag_tolerable  = (line_spacing_m / 4.0) / vel_ms
    decision       = 'LAG_SIGNIFICANT' if abs(lag_median) >= lag_tolerable else 'LAG_NEGLIGIBLE'

    sep = '─' * 50
    print(f"\n[M2 LAG] {sep}")
    print(f"[M2 LAG] Lag mediano   : {lag_median:+.3f} s")
    print(f"[M2 LAG] Lag std       : {lag_std:.3f} s")
    print(f"[M2 LAG] Lag tolerable : {lag_tolerable:.3f} s  (= spacing/4 / v)")
    print(f"[M2 LAG] Pares usados  : {len(lags)}")
    print(f"[M2 LAG] Decisión      : {decision}")
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
        print("[M2 LAG] No se pudo calcular dt_medio. Corrección no aplicada.")
        df['lag_applied'] = False
        return df

    lag_samples = int(round(lag_s / dt_medio_s))

    print(f"[M2 LAG] Corrección: lag = {lag_s:.3f} s  →  {lag_samples} muestras  "
          f"(dt = {dt_medio_s * 1000:.1f} ms)")

    if lag_samples == 0:
        print("[M2 LAG] lag_samples = 0, sin corrección necesaria.")
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
    print(f"[M2 LAG] Columnas GPS ajustadas  : {col_gps}")
    print(f"[M2 LAG] Muestras marcadas NaN   : {n_inv}")
    return df


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

    p_e = _perfil_weste_este(seg_e, paso_m)
    p_o = _perfil_weste_este(seg_o, paso_m)

    if p_e is None or p_o is None:
        print("[M2 LAG] No hay datos suficientes para el diagnóstico.")
        return

    n = min(len(p_e), len(p_o))
    p_e = p_e[:n]
    p_o = p_o[:n]

    # Offset de la cross-correlación (en muestras del perfil espacial)
    corr     = np.correlate(p_e, p_o, mode='full')
    lags_idx = np.arange(-(n - 1), n)
    lag_peak_samples = int(lags_idx[np.argmax(corr)])

    lid_e = int(seg_e['line_id'].iloc[0])
    lid_o = int(seg_o['line_id'].iloc[0])
    dist  = np.arange(n) * paso_m

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    fig.suptitle(
        f"Diagnóstico de lag  |  Línea {lid_e} (E→) vs Línea {lid_o} (←O)  "
        f"|  lag = {lag_s:+.3f} s",
        fontsize=12,
    )

    # --- Panel 1: sin corrección ---
    ax = axes[0]
    ax.set_title("Antes de corrección (desplazamiento visible entre anomalías)")
    ax.plot(dist, p_e, color='steelblue',  linewidth=0.9, label=f'Línea {lid_e} (E→)')
    ax.plot(dist, p_o, color='darkorange', linewidth=0.9, label=f'Línea {lid_o} (←O invertida W→E)')
    ax.set_ylabel('Mag1C (nT, centrada)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    desplaz_m = abs(lag_peak_samples) * paso_m
    ax.annotate(
        f'Desplazamiento observado ≈ {desplaz_m:.0f} m ({lag_peak_samples} muestras)',
        xy=(0.02, 0.97), xycoords='axes fraction', va='top', fontsize=8,
    )

    # --- Panel 2: con corrección (alineación por shift de correlación) ---
    ax = axes[1]
    ax.set_title("Después de corrección (perfil O alineado con E)")

    ls = lag_peak_samples
    if ls > 0:
        # p_o a la derecha de p_e → desplazar p_o hacia la izquierda
        p_o_alin = np.empty(n)
        p_o_alin[:n - ls] = p_o[ls:]
        p_o_alin[n - ls:] = np.nan
    elif ls < 0:
        ls_abs = abs(ls)
        p_o_alin = np.empty(n)
        p_o_alin[:ls_abs] = np.nan
        p_o_alin[ls_abs:] = p_o[:n - ls_abs]
    else:
        p_o_alin = p_o.copy()

    ax.plot(dist, p_e,      color='steelblue',  linewidth=0.9, label=f'Línea {lid_e} (E→)')
    ax.plot(dist, p_o_alin, color='darkorange', linewidth=0.9, label=f'Línea {lid_o} (alineada)')
    ax.set_ylabel('Mag1C (nT, centrada)')
    ax.set_xlabel('Distancia acumulada (m)')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  [M2 LAG] Diagnóstico guardado: {output_path}")
