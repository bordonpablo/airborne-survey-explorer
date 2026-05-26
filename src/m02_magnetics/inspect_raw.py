"""
Module 2 — Inspección visual de señal magnética cruda vs compensada.

Genera un PNG de 4 paneles por cada línea de vuelo, con eje x compartido
igual a la distancia acumulada a lo largo de la línea (m):
    Panel 1 — Campo total: Mag1/Mag1C y Mag2/Mag2C (raw vs compensado)
    Panel 2 — Gradiente: MagL y MagLC (raw vs compensado)
    Panel 3 — Actitud: Roll, Pitch (eje izq.) y Yaw (eje der.)
    Panel 4 — Altimetría: Ralt, Lalt (si válido), referencia en altura nominal

También genera un PNG resumen por vuelo con el Panel 1 de todas las líneas
en una grilla de miniaturas.

Uso:
    python -m src.m02_magnetics.inspect_raw 22.04.2022 00447
    python -m src.m02_magnetics.inspect_raw 22.04.2022 00447 1001
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def _distancia_acumulada_m(df: pd.DataFrame) -> np.ndarray:
    """Distancia haversine acumulada a lo largo de la línea (metros)."""
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6_371_000.0 * np.sqrt(dlat**2 + (np.cos(lat_mid) * dlon)**2)
    return np.concatenate([[0.0], np.cumsum(d)])


def _tiene_datos(seg: pd.DataFrame, col: str) -> bool:
    return col in seg.columns and seg[col].notna().any()


def graficar_linea(seg: pd.DataFrame, nominal_alt: float, out_path: Path) -> None:
    """
    PNG de 4 paneles para una línea de vuelo: campo total, gradiente, actitud, altimetría.

    El geofísico usa esta figura para evaluar la calidad de la compensación en tiempo
    real antes de aplicar correcciones adicionales.
    """
    seg = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps'])
    dist = _distancia_acumulada_m(seg)
    flight_id = seg['flight_id'].iloc[0]
    line_id = int(seg['line_id'].iloc[0])

    fig, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True)
    fig.suptitle(
        f"Flight {flight_id}  |  Line {line_id}  |  Raw vs Compensated",
        fontsize=13,
    )

    # --- Panel 1: Campo total ---
    ax = axes[0]
    if _tiene_datos(seg, 'Mag1'):
        ax.plot(dist, seg['Mag1'].values, color='#c0c0c0', linewidth=0.7, label='Mag1 raw')
    if _tiene_datos(seg, 'Mag1C'):
        ax.plot(dist, seg['Mag1C'].values, color='steelblue', linewidth=0.9, label='Mag1C comp')
    if _tiene_datos(seg, 'Mag2'):
        ax.plot(dist, seg['Mag2'].values, color='#d8d8d8', linewidth=0.7, label='Mag2 raw')
    if _tiene_datos(seg, 'Mag2C'):
        ax.plot(dist, seg['Mag2C'].values, color='darkorange', linewidth=0.9, label='Mag2C comp')

    notas = []
    if _tiene_datos(seg, 'Mag1') and _tiene_datos(seg, 'Mag1C'):
        d1 = seg['Mag1C'].mean() - seg['Mag1'].mean()
        notas.append(f'ΔMag1C−Mag1 = {d1:+.1f} nT')
    if _tiene_datos(seg, 'Mag2') and _tiene_datos(seg, 'Mag2C'):
        d2 = seg['Mag2C'].mean() - seg['Mag2'].mean()
        notas.append(f'ΔMag2C−Mag2 = {d2:+.1f} nT')
    if notas:
        ax.annotate('   '.join(notas), xy=(0.02, 0.97), xycoords='axes fraction',
                    va='top', fontsize=8)

    ax.set_ylabel('Campo total (nT)')
    ax.legend(fontsize=8, loc='upper right', ncol=2)
    ax.grid(True, alpha=0.3)

    # --- Panel 2: Gradiente ---
    ax = axes[1]
    if _tiene_datos(seg, 'MagL'):
        ax.plot(dist, seg['MagL'].values, color='#bbbbbb', linewidth=0.7, label='MagL raw')
    if _tiene_datos(seg, 'MagLC'):
        ax.plot(dist, seg['MagLC'].values, color='seagreen', linewidth=0.9, label='MagLC comp')
    ax.axhline(0, color='gray', linewidth=0.5, linestyle='--')

    if _tiene_datos(seg, 'MagLC'):
        std_lc = seg['MagLC'].std()
        ax.annotate(f'std(MagLC) = {std_lc:.2f} nT', xy=(0.02, 0.97),
                    xycoords='axes fraction', va='top', fontsize=8, color='seagreen')

    ax.set_ylabel('Gradiente (nT)')
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

    # --- Panel 3: Actitud ---
    ax = axes[2]
    ax_yaw = ax.twinx()

    if _tiene_datos(seg, 'Roll'):
        ax.plot(dist, seg['Roll'].values, color='steelblue', linewidth=0.8, label='Roll')
    if _tiene_datos(seg, 'Pitch'):
        ax.plot(dist, seg['Pitch'].values, color='darkorange', linewidth=0.8, label='Pitch')
    ax.axhline(0, color='gray', linewidth=0.5, linestyle='--')
    ax.set_ylabel('Roll / Pitch (°)')

    if _tiene_datos(seg, 'Yaw'):
        ax_yaw.plot(dist, seg['Yaw'].values, color='seagreen', linewidth=0.8,
                    label='Yaw', alpha=0.7)
    ax_yaw.set_ylabel('Yaw (°)', color='seagreen')
    ax_yaw.tick_params(axis='y', labelcolor='seagreen')

    lineas1, etiq1 = ax.get_legend_handles_labels()
    lineas2, etiq2 = ax_yaw.get_legend_handles_labels()
    ax.legend(lineas1 + lineas2, etiq1 + etiq2, fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

    # --- Panel 4: Altimetría ---
    ax = axes[3]
    if _tiene_datos(seg, 'Ralt'):
        ax.plot(dist, seg['Ralt'].values, color='steelblue', linewidth=0.8, label='Ralt (radar)')

    if 'Lalt' in seg.columns:
        lalt_valido = seg['Lalt'].dropna()
        if len(lalt_valido) > 10 and lalt_valido.std() > 0.1:
            ax.plot(dist, seg['Lalt'].values, color='darkorange', linewidth=0.8,
                    label='Lalt (láser)', alpha=0.9)

    ax.axhline(nominal_alt, color='red', linewidth=0.8, linestyle='--',
               label=f'Nominal {nominal_alt} m')
    ax.set_ylabel('Altitud (m)')
    ax.set_xlabel('Distancia acumulada (m)')
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  [M2] Guardado: {out_path}")


def graficar_resumen(on_line: pd.DataFrame, flight_id: str, out_path: Path) -> None:
    """
    PNG resumen por vuelo: Panel 1 (campo total) en miniatura para cada línea.

    Permite ver de un vistazo si la compensación es consistente entre líneas
    y detectar líneas problemáticas antes de inspeccionar en detalle.
    """
    line_ids = sorted(on_line['line_id'].unique())
    n = len(line_ids)
    if n == 0:
        return

    ncols = min(3, n)
    nrows = (n + ncols - 1) // ncols

    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 3 * nrows), squeeze=False)
    fig.suptitle(f"Flight {flight_id} — Campo total (resumen de líneas)", fontsize=12)

    for idx, lid in enumerate(line_ids):
        r, c = divmod(idx, ncols)
        ax = axes[r][c]
        seg = on_line[on_line['line_id'] == lid].sort_values('M3clk').dropna(
            subset=['Xgps', 'Ygps']
        )
        dist = _distancia_acumulada_m(seg)

        if _tiene_datos(seg, 'Mag1'):
            ax.plot(dist, seg['Mag1'].values, color='#c0c0c0', linewidth=0.5)
        if _tiene_datos(seg, 'Mag1C'):
            ax.plot(dist, seg['Mag1C'].values, color='steelblue', linewidth=0.7)
        if _tiene_datos(seg, 'Mag2'):
            ax.plot(dist, seg['Mag2'].values, color='#d8d8d8', linewidth=0.5)
        if _tiene_datos(seg, 'Mag2C'):
            ax.plot(dist, seg['Mag2C'].values, color='darkorange', linewidth=0.7)

        ax.set_title(f"Line {int(lid)}", fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    # Ocultar subplots vacíos
    for idx in range(n, nrows * ncols):
        r, c = divmod(idx, ncols)
        axes[r][c].set_visible(False)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120, bbox_inches='tight')
    plt.close(fig)
    print(f"  [M2] Resumen guardado: {out_path}")


def imprimir_resumen(on_line: pd.DataFrame, flight_id: str, date: str) -> None:
    filas = []
    for lid, seg in on_line.groupby('line_id'):
        fila = {'line_id': int(lid), 'n_puntos': len(seg)}
        if _tiene_datos(seg, 'Mag1'):
            fila['mag1_rango_nT'] = round(seg['Mag1'].max() - seg['Mag1'].min(), 1)
        if _tiene_datos(seg, 'Mag1C'):
            fila['mag1c_std_nT'] = round(seg['Mag1C'].std(), 2)
        if _tiene_datos(seg, 'MagLC'):
            fila['maglc_std_nT'] = round(seg['MagLC'].std(), 2)
        filas.append(fila)
    print(f"\n[M2] Flight {flight_id} — {date}  ({on_line['line_id'].nunique()} líneas)\n")
    print(pd.DataFrame(filas).to_string(index=False))
    print()


def inspect(date: str, flight_id: str, line_id: int | None = None) -> None:
    cfg         = load_config()
    campaign    = cfg['campaign']['name']
    run_name    = cfg['campaign']['run_name']
    nominal_alt = cfg['survey_design']['nominal_altitude_m']

    parquet_path = (
        PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
        / date / f'flight_{flight_id}_prepared.parquet'
    )
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"Parquet no encontrado: {parquet_path}\n"
            "Ejecutar prepare.py primero."
        )

    df      = pd.read_parquet(parquet_path)
    on_line = df[df['line_id'].notna() & df['line_valid']].copy()

    if line_id is not None:
        on_line = on_line[on_line['line_id'] == line_id]
        if on_line.empty:
            raise ValueError(f"Sin datos válidos para la línea {line_id} en el vuelo {flight_id}.")

    out_base = (
        PROJECT_ROOT / 'outputs' / campaign / run_name
        / 'm02' / 'inspection' / date
    )

    imprimir_resumen(on_line, flight_id, date)

    for lid, seg in on_line.groupby('line_id'):
        out_path = out_base / f"flight_{flight_id}_line_{int(lid)}.png"
        graficar_linea(seg, nominal_alt, out_path)

    if line_id is None:
        out_resumen = out_base / f"flight_{flight_id}_summary.png"
        graficar_resumen(on_line, flight_id, out_resumen)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Uso: python -m src.m02_magnetics.inspect_raw <fecha> <flight_id> [line_id]")
        sys.exit(1)
    date_arg   = sys.argv[1]
    flight_arg = sys.argv[2].zfill(5)
    line_arg   = int(sys.argv[3]) if len(sys.argv) > 3 else None
    inspect(date_arg, flight_arg, line_arg)
