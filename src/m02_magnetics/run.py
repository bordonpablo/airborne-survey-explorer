"""
Module 2 — Correcciones magnéticas: entrada principal.

Lee line_selection.csv y aplica la cadena de correcciones magnéticas a todos
los segmentos seleccionados en M1.

Input:
    data/interim/<campaign>/<run_name>/line_selection.csv
    data/interim/<campaign>/<run_name>/<date>/flight_XXXXX_prepared.parquet  (M0)

Output:
    data/interim/<campaign>/<run_name>/<date>/flight_XXXXX_m02.parquet
    outputs/<campaign>/<run_name>/m02/lag_report.json

Pasos implementados:
    1–2. Corrección de lag GPS-magnetómetro  (lag.py)

Pasos pendientes:
    3. Corrección diurna    (diurnal.py)
    4. Remoción IGRF        (igrf.py)
    5. Corrección heading   (heading.py)
    6. Promedio sensores    (average_sensors.py)
    7. Nivelación tie-lines (levelling.py)
    8. Micronivelación      (microlevelling.py)

Uso:
    python -m src.m02_magnetics.run              # toda la campaña
    python -m src.m02_magnetics.run 22.04.2022   # un día específico
"""

import json
import sys
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m02_magnetics.lag import estimate_lag, apply_lag


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def load_line_selection(interim_root: Path) -> pd.DataFrame:
    path = interim_root / 'line_selection.csv'
    if not path.exists():
        raise FileNotFoundError(
            f"line_selection.csv no encontrado: {path}\n"
            "Ejecutá primero: python -m src.m00_preparation.build_line_selection"
        )
    return pd.read_csv(path, dtype={'flight_id': str, 'line_id': int})


def main(target_date: str | None = None) -> None:
    cfg          = load_config()
    campaign     = cfg['campaign']['name']
    run_name     = cfg['campaign']['run_name']
    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
    out_root     = PROJECT_ROOT / 'outputs' / campaign / run_name / 'm02'

    print(f"Campaign : {campaign}")
    print(f"Run      : {run_name}")

    # ── Cargar selección de líneas ────────────────────────────────────────────
    line_sel = load_line_selection(interim_root)
    selected = line_sel[line_sel['selected'] == True].copy()
    if target_date:
        selected = selected[selected['date'] == target_date]
    if selected.empty:
        print("No hay líneas seleccionadas para procesar.")
        return
    print(f"Segmentos seleccionados: {len(selected)}")

    # ── Paso 1: Estimación de lag ─────────────────────────────────────────────
    print("\n── Paso 1: Estimación de lag GPS-magnetómetro ──────────────────────")

    parts = []
    for _, row in selected.iterrows():
        pq = interim_root / row['date'] / f"flight_{row['flight_id']}_prepared.parquet"
        if not pq.exists():
            print(f"  No encontrado: {pq}")
            continue
        df  = pd.read_parquet(pq)
        seg = df[(df['line_id'] == row['line_id']) & df['line_valid']]
        if not seg.empty:
            parts.append(seg)

    if not parts:
        print("No se cargaron segmentos — no se puede estimar el lag.")
        return

    df_all = pd.concat(parts, ignore_index=True)
    print(f"  {len(df_all):,} filas válidas de {len(parts)} segmentos cargadas")

    lag_result = estimate_lag(df_all, cfg)

    out_root.mkdir(parents=True, exist_ok=True)
    report_path = out_root / 'lag_report.json'
    with open(report_path, 'w') as f:
        json.dump(
            {k: float(v) if hasattr(v, '__float__') else v
             for k, v in lag_result.items()},
            f, indent=2,
        )
    print(f"  Reporte de lag: {report_path}")

    # ── Paso 2: Aplicar corrección de lag por vuelo ───────────────────────────
    print("\n── Paso 2: Aplicando corrección de lag ─────────────────────────────")

    flights = selected[['date', 'flight_id']].drop_duplicates()

    for _, frow in flights.iterrows():
        date = frow['date']
        fid  = frow['flight_id']
        pq_in  = interim_root / date / f"flight_{fid}_prepared.parquet"
        pq_out = interim_root / date / f"flight_{fid}_m02.parquet"

        if not pq_in.exists():
            print(f"  Saltando {date}/flight_{fid}: parquet M0 no encontrado")
            continue

        df_full = pd.read_parquet(pq_in)

        if lag_result['decision'] == 'LAG_SIGNIFICANT':
            df_out = apply_lag(df_full, lag_result['lag_median_s'])
        else:
            df_out = df_full.copy()
            df_out['lag_applied'] = False

        df_out.to_parquet(pq_out, index=False)
        print(f"  Guardado: {pq_out.relative_to(PROJECT_ROOT)}")

    sep = '─' * 55
    print(f"\n{sep}")
    print(f"  M2 pasos 1-2 completos.")
    print(f"  Decisión : {lag_result['decision']}")
    print(f"  Lag      : {lag_result['lag_median_s']:+.3f} s")
    print(f"  Salida   : data/interim/{campaign}/{run_name}/<date>/flight_XXXXX_m02.parquet")
    print(f"{sep}")


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(date_arg)
