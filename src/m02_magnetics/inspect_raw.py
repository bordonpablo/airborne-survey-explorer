"""
Module 2 — Raw signal inspection (before any correction).

Generates a 4-panel PNG per survey line, x-axis = cumulative distance along the line (m):
    Panel 1 — Total field: Mag1 / Mag1C and Mag2 / Mag2C (raw vs compensated)
    Panel 2 — Vertical gradient: MagL / MagLC (raw vs compensated)
    Panel 3 — Aircraft attitude: Roll, Pitch (left axis) and Yaw (right axis)
    Panel 4 — Altimetry: Ralt (radar), Lalt (laser, if valid), nominal drape altitude

Also generates one summary PNG per flight (Panel 1 thumbnails for every line).

Column reference
----------------
Mag1, Mag2   : raw total-field readings from the two scalar magnetometers (nT)
Mag1C, Mag2C : compensated field — aircraft interference removed by the onboard
               FOM/compensation system during flight (nT)
MagL         : raw vertical gradient = Mag1 − Mag2 (nT); bird vs stinger separation
MagLC        : compensated vertical gradient (nT)
Ralt         : radar altimeter — height above ground (m)
Lalt         : laser altimeter — height above ground (m), if fitted

Note: there is no pre-averaged magnetometer output from the aircraft.
The sensor average (step 6) is computed during M2 processing.

Usage
-----
    # All selected lines (reads line_selection.csv)
    python -m src.m02_magnetics.inspect_raw

    # One specific day
    python -m src.m02_magnetics.inspect_raw 22.04.2022

    # One specific flight
    python -m src.m02_magnetics.inspect_raw 22.04.2022 00447

    # One specific line
    python -m src.m02_magnetics.inspect_raw 22.04.2022 00447 1001
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import geopandas as gpd
from shapely.geometry import Point
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

    # --- Panel 1: Total field ---
    ax = axes[0]
    if _tiene_datos(seg, 'Mag1'):
        ax.plot(dist, seg['Mag1'].values, color='#c0c0c0', linewidth=0.7, label='Mag1 raw')
    if _tiene_datos(seg, 'Mag1C'):
        ax.plot(dist, seg['Mag1C'].values, color='steelblue', linewidth=0.9, label='Mag1C compensated')
    if _tiene_datos(seg, 'Mag2'):
        ax.plot(dist, seg['Mag2'].values, color='#d8d8d8', linewidth=0.7, label='Mag2 raw')
    if _tiene_datos(seg, 'Mag2C'):
        ax.plot(dist, seg['Mag2C'].values, color='darkorange', linewidth=0.9, label='Mag2C compensated')

    notes = []
    if _tiene_datos(seg, 'Mag1') and _tiene_datos(seg, 'Mag1C'):
        d1 = seg['Mag1C'].mean() - seg['Mag1'].mean()
        notes.append(f'ΔMag1C−Mag1 = {d1:+.1f} nT')
    if _tiene_datos(seg, 'Mag2') and _tiene_datos(seg, 'Mag2C'):
        d2 = seg['Mag2C'].mean() - seg['Mag2'].mean()
        notes.append(f'ΔMag2C−Mag2 = {d2:+.1f} nT')
    if notes:
        ax.annotate('   '.join(notes), xy=(0.02, 0.97), xycoords='axes fraction',
                    va='top', fontsize=8)

    ax.set_ylabel('Total field (nT)')
    ax.legend(fontsize=8, loc='upper right', ncol=2)
    ax.grid(True, alpha=0.3)

    # --- Panel 2: Vertical gradient ---
    ax = axes[1]
    if _tiene_datos(seg, 'MagL'):
        ax.plot(dist, seg['MagL'].values, color='#bbbbbb', linewidth=0.7, label='MagL raw (Mag1−Mag2)')
    if _tiene_datos(seg, 'MagLC'):
        ax.plot(dist, seg['MagLC'].values, color='seagreen', linewidth=0.9, label='MagLC compensated')
    ax.axhline(0, color='gray', linewidth=0.5, linestyle='--')

    if _tiene_datos(seg, 'MagLC'):
        std_lc = seg['MagLC'].std()
        ax.annotate(f'std(MagLC) = {std_lc:.2f} nT', xy=(0.02, 0.97),
                    xycoords='axes fraction', va='top', fontsize=8, color='seagreen')

    ax.set_ylabel('Vertical gradient (nT)')
    ax.legend(fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

    # --- Panel 3: Aircraft attitude ---
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

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax_yaw.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc='upper right')
    ax.grid(True, alpha=0.3)

    # --- Panel 4: Altimetry ---
    ax = axes[3]
    if _tiene_datos(seg, 'Ralt'):
        ax.plot(dist, seg['Ralt'].values, color='steelblue', linewidth=0.8, label='Ralt (radar)')

    if 'Lalt' in seg.columns:
        lalt_valid = seg['Lalt'].dropna()
        if len(lalt_valid) > 10 and lalt_valid.std() > 0.1:
            ax.plot(dist, seg['Lalt'].values, color='darkorange', linewidth=0.8,
                    label='Lalt (laser)', alpha=0.9)

    ax.axhline(nominal_alt, color='red', linewidth=0.8, linestyle='--',
               label=f'Nominal {nominal_alt} m')
    ax.set_ylabel('Altitude (m)')
    ax.set_xlabel('Cumulative distance (m)')
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
    fig.suptitle(f"Flight {flight_id} — Total field summary (all lines)", fontsize=12)

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
    print(f"\n[M2] Flight {flight_id} — {date}  ({on_line['line_id'].nunique()} lines)\n")
    print(pd.DataFrame(filas).to_string(index=False))
    print()


# Columns to map spatially. (sym=True → RdBu_r centred at 0; False → plasma)
_MAP_COLS = [
    ('Mag1',  'Mag1 — Raw total field (nT)',                False),
    ('Mag1C', 'Mag1C — Compensated total field (nT)',       False),
    ('Mag2',  'Mag2 — Raw total field (nT)',                False),
    ('Mag2C', 'Mag2C — Compensated total field (nT)',       False),
    ('MagL',  'MagL — Raw vertical gradient (nT)',          True),
    ('MagLC', 'MagLC — Compensated vertical gradient (nT)', True),
]


def graficar_mapas_campo(on_line: pd.DataFrame, flight_id: str, out_path: Path) -> None:
    """
    Scatter maps of all magnetic columns in geographic coordinates (lon/lat).
    One subplot per column; x = longitude, y = latitude.
    Color limits use the 2nd–98th percentile to suppress outliers.
    """
    available = [(col, title, sym) for col, title, sym in _MAP_COLS
                 if col in on_line.columns and on_line[col].notna().any()]
    if not available:
        return

    n     = len(available)
    ncols = 3
    nrows = (n + ncols - 1) // ncols
    lat_mean = on_line['Ygps'].mean()
    aspect   = 1.0 / np.cos(np.radians(lat_mean))   # correct for lat compression

    fig, axes = plt.subplots(nrows, ncols, figsize=(7 * ncols, 6 * nrows))
    axes_flat  = np.array(axes).flatten() if n > 1 else [axes]

    for i, (col, title, sym) in enumerate(available):
        ax    = axes_flat[i]
        valid = on_line[['Xgps', 'Ygps', col]].dropna()
        p2, p98 = np.nanpercentile(valid[col], [2, 98])
        if sym:
            vabs = max(abs(p2), abs(p98))
            vmin, vmax, cmap = -vabs, vabs, 'RdBu_r'
        else:
            vmin, vmax, cmap = p2, p98, 'plasma'

        sc = ax.scatter(valid['Xgps'], valid['Ygps'], c=valid[col],
                        s=0.5, cmap=cmap, vmin=vmin, vmax=vmax, rasterized=True)
        cb = plt.colorbar(sc, ax=ax, shrink=0.8)
        cb.set_label('nT', fontsize=7)
        cb.ax.tick_params(labelsize=6)
        ax.set_aspect(aspect)
        ax.set_title(title, fontsize=8, pad=4)
        ax.set_xlabel('Longitude (°)', fontsize=7)
        ax.set_ylabel('Latitude (°)', fontsize=7)
        ax.tick_params(labelsize=6)
        ax.grid(alpha=0.3)

    for j in range(len(available), len(axes_flat)):
        axes_flat[j].set_visible(False)

    fig.suptitle(f'Flight {flight_id} — Field maps (raw and compensated)', fontsize=11)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  [M2] Field maps: {out_path}')


def exportar_geopackage(on_line: pd.DataFrame, flight_id: str, out_path: Path) -> None:
    """
    GeoPackage with one layer per magnetic column (WGS84 / EPSG:4326).
    Each layer contains all on-line points for the flight with that column's values.
    Open in QGIS to toggle layers and adjust colour scales independently.
    """
    base = on_line[['Xgps', 'Ygps', 'line_id', 'flight_id']].dropna(subset=['Xgps', 'Ygps']).copy()
    geometry = [Point(lon, lat) for lon, lat in zip(base['Xgps'], base['Ygps'])]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    first = True
    for col, _, _ in _MAP_COLS:
        if col not in on_line.columns:
            continue
        sub = base.copy()
        sub[col] = on_line.loc[base.index, col].values
        gdf  = gpd.GeoDataFrame(sub, geometry=geometry, crs='EPSG:4326')
        mode = 'w' if first else 'a'
        gdf.to_file(out_path, driver='GPKG', layer=col, mode=mode)
        first = False

    print(f'  [M2] GeoPackage:  {out_path}')


def inspect(date: str, flight_id: str, line_id: int | None = None) -> None:
    cfg         = load_config()
    campaign    = cfg['campaign']['name']
    run_name    = cfg['campaign']['run_name']
    nominal_alt = cfg['survey_design']['nominal_altitude_m']

    parquet_path = (
        PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
        / 'm00' / date / f'flight_{flight_id}_prepared.parquet'
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


def inspect_all() -> None:
    """
    Load all selected lines from line_selection.csv, generate per-line profile
    PNGs, and produce ONE consolidated field-map PNG and GeoPackage for the
    entire campaign.

    The consolidated outputs are what matters at M2 stage — line selection was
    already decided in M0/M1.
    """
    cfg          = load_config()
    campaign     = cfg['campaign']['name']
    run_name     = cfg['campaign']['run_name']
    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
    out_base     = PROJECT_ROOT / 'outputs' / campaign / run_name / 'm02' / 'inspection'
    sel_path     = interim_root / 'line_selection.csv'

    if not sel_path.exists():
        print(f"line_selection.csv not found: {sel_path}")
        sys.exit(1)

    sel     = pd.read_csv(sel_path, dtype={'flight_id': str})
    sel     = sel[sel['selected'] == True]
    flights = sel[['date', 'flight_id']].drop_duplicates()
    print(f"Selected: {len(sel)} lines across {len(flights)} flights.")

    # ── Per-line profile PNGs ─────────────────────────────────────────────────
    print("\n── Per-line profile plots ──────────────────────────────────────────")
    all_segments = []
    for _, row in flights.iterrows():
        inspect(row['date'], row['flight_id'])

        # Collect selected segments for consolidated outputs
        pq = interim_root / 'm00' / row['date'] / f"flight_{row['flight_id']}_prepared.parquet"
        if not pq.exists():
            continue
        df       = pd.read_parquet(pq)
        line_ids = sel[sel['flight_id'] == row['flight_id']]['line_id'].tolist()
        seg      = df[df['line_id'].isin(line_ids) & df['line_valid']].copy()
        if not seg.empty:
            all_segments.append(seg)

    if not all_segments:
        print("No segments loaded — nothing to consolidate.")
        return

    df_all = pd.concat(all_segments, ignore_index=True)
    n_lines = df_all['line_id'].nunique()
    print(f"\n── Consolidated outputs ({len(df_all):,} points, {n_lines} lines) ──────")

    # ── Consolidated field maps ───────────────────────────────────────────────
    out_maps = out_base / 'campaign_field_maps.png'
    graficar_mapas_campo(df_all, 'campaign', out_maps)

    # ── Consolidated GeoPackage ───────────────────────────────────────────────
    out_gpkg = out_base / 'campaign_raw.gpkg'
    exportar_geopackage(df_all, 'campaign', out_gpkg)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        inspect_all()
    elif len(sys.argv) == 2:
        inspect(sys.argv[1], None)
    else:
        date_arg   = sys.argv[1]
        flight_arg = sys.argv[2].zfill(5)
        line_arg   = int(sys.argv[3]) if len(sys.argv) > 3 else None
        inspect(date_arg, flight_arg, line_arg)
