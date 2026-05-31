"""
Module 2 — Magnetic corrections: main entry point.

Reads line_selection.csv and applies the magnetic correction chain to all
segments selected in M1.

Input:
    data/interim/<campaign>/<run_name>/line_selection.csv
    data/interim/<campaign>/<run_name>/m00/<date>/flight_XXXXX_prepared.parquet  (M0)

Output:
    data/interim/<campaign>/<run_name>/m02/<date>/flight_XXXXX_m02.parquet
    outputs/<campaign>/<run_name>/m02/lag_report.json
    outputs/<campaign>/<run_name>/m02/campaign_m02.gpkg   (all selected lines)

Steps implemented:
    1–2. GPS lag correction   (lag.py)
    3.   Diurnal correction   (diurnal.py)
    4.   IGRF removal         (igrf.py)
    5.   Heading correction   (heading.py)
    6.   Sensor average       (average_sensors.py)
    7.   Tie-line levelling   (levelling.py)
    8.   Micro-levelling      (microlevelling.py)
    7. Tie-line levelling     (levelling.py)
    8. Micro-levelling        (microlevelling.py)
    4. IGRF removal          (igrf.py)
    5. Heading correction    (heading.py)
    6. Sensor average        (average_sensors.py)
    7. Tie-line levelling    (levelling.py)
    8. Micro-levelling       (microlevelling.py)

Usage:
    python -m src.m02_magnetics.run                        # all implemented steps, full campaign
    python -m src.m02_magnetics.run --steps 1,2            # lag only
    python -m src.m02_magnetics.run --steps 3              # diurnal only (lag must already be done)
    python -m src.m02_magnetics.run --steps 1,2,3          # lag + diurnal
    python -m src.m02_magnetics.run 22.04.2022 --steps 1,2 # lag only, one day
"""

import argparse
import json
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

from src.m02_magnetics.lag import estimate_lag, apply_lag, plot_lag_diagnosis
from src.m02_magnetics.diurnal import find_tagesgang, apply_diurnal
from src.m02_magnetics.igrf import apply_igrf
from src.m02_magnetics.heading import estimate_heading_bias, apply_heading
from src.m02_magnetics.average_sensors import apply_sensor_average
from src.m02_magnetics.levelling import compute_crossover_offsets, apply_levelling
from src.m02_magnetics.microlevelling import apply_microlevelling
from src.m00_preparation.read_tagesgang import read_tagesgang


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def load_line_selection(interim_root: Path) -> pd.DataFrame:
    path = interim_root / 'line_selection.csv'
    if not path.exists():
        raise FileNotFoundError(
            f"line_selection.csv not found: {path}\n"
            "Run build_line_selection.py first."
        )
    return pd.read_csv(path, dtype={'flight_id': str, 'line_id': int})


def plot_campaign_map(
    selected: pd.DataFrame,
    interim_root: Path,
    lag_result: dict,
    out_path: Path,
) -> None:
    """
    Scatter map of all selected lines after lag correction, coloured by Mag1C.

    Shows spatial coverage and signal level across the campaign.
    A second panel shows Mag2C for quick sensor comparison.
    """
    parts = []
    for _, row in selected.iterrows():
        pq = interim_root / 'm02' / row['date'] / f"flight_{row['flight_id']}_m02.parquet"
        if not pq.exists():
            pq = interim_root / 'm00' / row['date'] / f"flight_{row['flight_id']}_prepared.parquet"
        if not pq.exists():
            continue
        df  = pd.read_parquet(pq)
        seg = df[(df['line_id'] == row['line_id']) & df['line_valid']].copy()
        if not seg.empty:
            parts.append(seg)

    if not parts:
        print("  [map] No data to plot.")
        return

    df_all   = pd.concat(parts, ignore_index=True)
    lat_mean = df_all['Ygps'].mean()
    aspect   = 1.0 / np.cos(np.radians(lat_mean))

    cols_to_plot = [(c, c) for c in ['Mag1C', 'Mag2C'] if c in df_all.columns]
    if not cols_to_plot:
        cols_to_plot = [('Mag1', 'Mag1')]

    fig, axes = plt.subplots(1, len(cols_to_plot), figsize=(9 * len(cols_to_plot), 8))
    if len(cols_to_plot) == 1:
        axes = [axes]

    decision = lag_result.get('decision', '')
    lag_s    = lag_result.get('lag_median_s', 0.0)

    for ax, (col, label) in zip(axes, cols_to_plot):
        valid = df_all[['Xgps', 'Ygps', col]].dropna()
        p2, p98 = np.nanpercentile(valid[col], [2, 98])
        sc = ax.scatter(
            valid['Xgps'], valid['Ygps'], c=valid[col],
            s=0.4, cmap='plasma', vmin=p2, vmax=p98, rasterized=True,
        )
        cb = plt.colorbar(sc, ax=ax, shrink=0.8)
        cb.set_label('nT', fontsize=8)
        ax.set_aspect(aspect)
        ax.set_title(f'{label} — compensated total field', fontsize=9)
        ax.set_xlabel('Longitude (°)', fontsize=8)
        ax.set_ylabel('Latitude (°)', fontsize=8)
        ax.grid(alpha=0.3)

    n_lines  = df_all['line_id'].nunique()
    n_points = len(df_all)
    fig.suptitle(
        f'Campaign overview after lag correction  |  {n_lines} lines  |  {n_points:,} points\n'
        f'Lag: {lag_s:+.3f} s  —  {decision}',
        fontsize=10,
    )
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Campaign map: {out_path.relative_to(PROJECT_ROOT)}")


def plot_lag_diagnostic(
    df_all: pd.DataFrame,
    lag_result: dict,
    out_root: Path,
) -> None:
    """
    Call plot_lag_diagnosis for the E/W pair with the highest point count.
    Skips silently if no pairs are available or lag is negligible.
    """
    from src.m02_magnetics.lag import _identificar_pares, _velocidad_media_ms

    if lag_result.get('decision') == 'LAG_UNKNOWN':
        return

    cfg_path = PROJECT_ROOT / 'config' / 'project.yaml'
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    pares = _identificar_pares(df_all, cfg['survey_design']['line_spacing_m'])
    if not pares:
        return

    vel_ms = _velocidad_media_ms(df_all)
    paso_m = vel_ms * 0.1

    # Pick the pair with the most combined points
    best_pair = max(
        pares,
        key=lambda p: len(df_all[
            (df_all['flight_id'] == p[0]['flight_id']) &
            (df_all['line_id']   == p[0]['line_id'])
        ]) + len(df_all[
            (df_all['flight_id'] == p[1]['flight_id']) &
            (df_all['line_id']   == p[1]['line_id'])
        ]),
    )
    fe, fo = best_pair
    seg_e = df_all[
        (df_all['flight_id'] == fe['flight_id']) &
        (df_all['line_id']   == fe['line_id']) &
        df_all['line_valid']
    ].copy()
    seg_o = df_all[
        (df_all['flight_id'] == fo['flight_id']) &
        (df_all['line_id']   == fo['line_id']) &
        df_all['line_valid']
    ].copy()

    out_path = out_root / f"lag_diagnosis_line{int(fe['line_id'])}_line{int(fo['line_id'])}.png"
    plot_lag_diagnosis(seg_e, seg_o, lag_result['lag_median_s'], out_path, paso_m)


def export_step_output(
    selected: pd.DataFrame,
    interim_root: Path,
    out_root: Path,
    step_name: str,
    cols: list[str],
) -> None:
    """
    Generate a per-step GeoPackage and map PNG showing the columns produced
    at this correction step (typically: input column + output column).

    Files are named step_<step_name>.gpkg / step_<step_name>_map.png so they
    never overwrite outputs from other steps.

    Parameters
    ----------
    cols : columns to export, in order. First = before correction, last = after.
    """
    parts = []
    for _, row in selected.iterrows():
        pq = interim_root / 'm02' / row['date'] / f"flight_{row['flight_id']}_m02.parquet"
        if not pq.exists():
            continue
        df  = pd.read_parquet(pq)
        seg = df[(df['line_id'] == row['line_id']) & df['line_valid']].copy()
        if not seg.empty:
            parts.append(seg)

    if not parts:
        return

    df_all   = pd.concat(parts, ignore_index=True)
    df_all   = df_all.dropna(subset=['Xgps', 'Ygps'])
    available = [c for c in cols if c in df_all.columns]
    if not available:
        return

    geometry = [Point(lon, lat) for lon, lat in zip(df_all['Xgps'], df_all['Ygps'])]
    id_base  = df_all[['flight_id', 'line_id']].copy()

    # ── GeoPackage ────────────────────────────────────────────────────────────
    gpkg_path = out_root / f'step_{step_name}.gpkg'
    if gpkg_path.exists():
        gpkg_path.unlink()
    first = True
    for col in available:
        sub  = id_base.copy()
        sub[col] = df_all[col].values
        gdf  = gpd.GeoDataFrame(sub, geometry=geometry, crs='EPSG:4326')
        gdf.to_file(gpkg_path, driver='GPKG', layer=col, mode='w' if first else 'a')
        first = False
    print(f"  Step GeoPackage: {gpkg_path.relative_to(PROJECT_ROOT)}")

    # ── Map PNG ───────────────────────────────────────────────────────────────
    lat_mean = df_all['Ygps'].mean()
    aspect   = 1.0 / np.cos(np.radians(lat_mean))
    n        = len(available)
    fig, axes = plt.subplots(1, n, figsize=(9 * n, 7))
    if n == 1:
        axes = [axes]

    sym_cols = {'Mag1_Diurnal', 'Mag2_Diurnal', 'Mag1_IGRF', 'Mag2_IGRF',
                'Mag1_IGRF_head', 'Mag2_IGRF_head', 'Mag_IGRF_head',
                'Mag_IGRF_head_level', 'Mag_Final'}

    for ax, col in zip(axes, available):
        valid = df_all[['Xgps', 'Ygps', col]].dropna()
        p2, p98 = np.nanpercentile(valid[col], [2, 98])
        if col in sym_cols:
            vabs = max(abs(p2), abs(p98))
            vmin, vmax, cmap = -vabs, vabs, 'RdBu_r'
        else:
            vmin, vmax, cmap = p2, p98, 'plasma'
        sc = ax.scatter(valid['Xgps'], valid['Ygps'], c=valid[col],
                        s=0.4, cmap=cmap, vmin=vmin, vmax=vmax, rasterized=True)
        cb = plt.colorbar(sc, ax=ax, shrink=0.8)
        cb.set_label('nT', fontsize=7)
        ax.set_aspect(aspect)
        ax.set_title(col, fontsize=9)
        ax.set_xlabel('Longitude (°)', fontsize=7)
        ax.set_ylabel('Latitude (°)', fontsize=7)
        ax.grid(alpha=0.3)

    fig.suptitle(f'Step {step_name} — {" → ".join(available)}', fontsize=10)
    plt.tight_layout()
    map_path = out_root / f'step_{step_name}_map.png'
    fig.savefig(map_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Step map:        {map_path.relative_to(PROJECT_ROOT)}")


def export_geopackage(
    selected: pd.DataFrame,
    interim_root: Path,
    out_path: Path,
    parquet_suffix: str = '_m02',
) -> None:
    """
    Export all selected lines from the m02 parquets as a consolidated
    GeoPackage (EPSG:4326). One layer per magnetic column.
    """
    # All magnetic columns in processing order — export whichever exist in the parquet
    mag_cols = [
        'Mag1',               'Mag2',               # raw
        'Mag1C',              'Mag2C',               # compensated (aircraft removed)
        'MagL',               'MagLC',               # gradient
        'Mag1_Diurnal',       'Mag2_Diurnal',        # after step 3
        'Mag1_IGRF',          'Mag2_IGRF',           # after step 4
        'Mag1_IGRF_head',     'Mag2_IGRF_head',      # after step 5
        'Mag_IGRF_head',                             # after step 6 (average)
        'Mag_IGRF_head_level',                       # after step 7
        'Mag_Final',                                 # after step 8
    ]
    id_cols  = ['flight_id', 'line_id', 'lag_applied']

    parts = []
    for _, row in selected.iterrows():
        pq = interim_root / 'm02' / row['date'] / f"flight_{row['flight_id']}{parquet_suffix}.parquet"
        if not pq.exists():
            continue
        df  = pd.read_parquet(pq)
        seg = df[(df['line_id'] == row['line_id']) & df['line_valid']].copy()
        if not seg.empty:
            parts.append(seg)

    if not parts:
        print("  [GeoPackage] No segments found — skipping.")
        return

    df_all   = pd.concat(parts, ignore_index=True)
    df_all   = df_all.dropna(subset=['Xgps', 'Ygps'])
    geometry = [Point(lon, lat) for lon, lat in zip(df_all['Xgps'], df_all['Ygps'])]

    keep_ids = [c for c in id_cols if c in df_all.columns]
    base     = df_all[keep_ids + ['Xgps', 'Ygps']].copy()

    if out_path.exists():
        out_path.unlink()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    first = True
    for col in mag_cols:
        if col not in df_all.columns:
            continue
        sub = base.copy()
        sub[col] = df_all[col].values
        gdf  = gpd.GeoDataFrame(sub, geometry=geometry, crs='EPSG:4326')
        mode = 'w' if first else 'a'
        gdf.to_file(out_path, driver='GPKG', layer=col, mode=mode)
        first = False

    print(f"  GeoPackage: {out_path.relative_to(PROJECT_ROOT)}  "
          f"({len(df_all):,} points, {df_all['line_id'].nunique()} lines)")


IMPLEMENTED_STEPS = {1, 2, 3, 4, 5, 6, 7, 8}


def main(target_date: str | None = None, steps: set[int] | None = None) -> None:
    if steps is None:
        steps = IMPLEMENTED_STEPS

    cfg          = load_config()
    campaign     = cfg['campaign']['name']
    run_name     = cfg['campaign']['run_name']
    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
    out_root     = PROJECT_ROOT / 'outputs' / campaign / run_name / 'm02'
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"Campaign : {campaign}")
    print(f"Run      : {run_name}")
    print(f"Steps    : {sorted(steps)}")

    line_sel = load_line_selection(interim_root)
    selected = line_sel[line_sel['selected'] == True].copy()
    if target_date:
        selected = selected[selected['date'] == target_date]
    if selected.empty:
        print("No selected lines to process.")
        return
    print(f"Selected segments: {len(selected)}")

    flights = selected[['date', 'flight_id']].drop_duplicates()

    # ── Steps 1–2: Lag correction ─────────────────────────────────────────────
    if 1 in steps or 2 in steps:
        print("\n── Step 1: GPS–magnetometer lag estimation ─────────────────────────")
        parts = []
        for _, row in selected.iterrows():
            pq = interim_root / 'm00' / row['date'] / f"flight_{row['flight_id']}_prepared.parquet"
            if not pq.exists():
                print(f"  Not found: {pq}")
                continue
            df  = pd.read_parquet(pq)
            seg = df[(df['line_id'] == row['line_id']) & df['line_valid']]
            if not seg.empty:
                parts.append(seg)

        if not parts:
            print("No segments loaded — cannot estimate lag.")
            return

        df_all     = pd.concat(parts, ignore_index=True)
        print(f"  {len(df_all):,} valid rows from {len(parts)} segments")
        lag_result = estimate_lag(df_all, cfg)

        report_path = out_root / 'lag_report.json'
        with open(report_path, 'w') as f:
            json.dump(
                {k: float(v) if hasattr(v, '__float__') else v
                 for k, v in lag_result.items()},
                f, indent=2,
            )
        print(f"  Lag report: {report_path.relative_to(PROJECT_ROOT)}")

        print("\n── Step 2: Applying lag correction ────────────────────────────────")
        for _, frow in flights.iterrows():
            date   = frow['date']
            fid    = frow['flight_id']
            pq_in  = interim_root / 'm00' / date / f"flight_{fid}_prepared.parquet"
            pq_out = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"

            if not pq_in.exists():
                print(f"  Skipping {date}/flight_{fid}: M0 parquet not found")
                continue

            df_full = pd.read_parquet(pq_in)
            if lag_result['decision'] == 'LAG_SIGNIFICANT':
                df_out = apply_lag(df_full, lag_result['lag_median_s'])
            else:
                df_out = df_full.copy()
                df_out['lag_applied'] = False

            pq_out.parent.mkdir(parents=True, exist_ok=True)
            df_out.to_parquet(pq_out, index=False)
            print(f"  Saved: {pq_out.relative_to(PROJECT_ROOT)}")

        print(f"\n  Lag decision : {lag_result['decision']}")
        print(f"  Lag value    : {lag_result['lag_median_s']:+.3f} s")

        plot_lag_diagnostic(df_all, lag_result, out_root)
        export_step_output(selected, interim_root, out_root,
                           '02_lag', ['Mag1C', 'Mag2C'])
    else:
        # Load lag result from previous run if skipping steps 1-2
        report_path = out_root / 'lag_report.json'
        if report_path.exists():
            with open(report_path) as f:
                lag_result = json.load(f)
        else:
            lag_result = {'decision': 'LAG_UNKNOWN', 'lag_median_s': 0.0}

    # ── Step 3: Diurnal correction ────────────────────────────────────────────
    if 3 in steps:
        print("\n── Step 3: Diurnal correction ───────────────────────────────────────")
        raw_root  = PROJECT_ROOT / cfg['campaign']['raw_data_path']
        igrf_base = cfg['magnetics']['igrf_base_field_nT']

        for _, frow in flights.iterrows():
            date = frow['date']
            fid  = frow['flight_id']
            pq   = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"

            if not pq.exists():
                print(f"  Skipping {date}/flight_{fid}: m02 parquet not found — run steps 1,2 first")
                continue

            try:
                tag_path = find_tagesgang(raw_root, date)
            except FileNotFoundError as e:
                print(f"  Skipping {date}/flight_{fid}: {e}")
                continue

            tag_df  = read_tagesgang(tag_path)
            df_full = pd.read_parquet(pq)
            df_out  = apply_diurnal(df_full, tag_df, igrf_base)
            df_out.to_parquet(pq, index=False)
            print(f"  Updated: {pq.relative_to(PROJECT_ROOT)}")

        export_step_output(selected, interim_root, out_root,
                           '03_diurnal', ['Mag1C', 'Mag1_Diurnal'])

    # ── Step 4: IGRF removal ──────────────────────────────────────────────────
    if 4 in steps:
        print("\n── Step 4: IGRF removal ─────────────────────────────────────────────")

        for _, frow in flights.iterrows():
            date = frow['date']
            fid  = frow['flight_id']
            pq   = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"

            if not pq.exists():
                print(f"  Skipping {date}/flight_{fid}: m02 parquet not found — run steps 1,2,3 first")
                continue

            df_full = pd.read_parquet(pq)

            if 'Mag1_Diurnal' not in df_full.columns:
                print(f"  Skipping {date}/flight_{fid}: Mag1_Diurnal not found — run step 3 first")
                continue

            df_out = apply_igrf(df_full, date)
            df_out.to_parquet(pq, index=False)
            print(f"  Updated: {pq.relative_to(PROJECT_ROOT)}")

        export_step_output(selected, interim_root, out_root,
                           '04_igrf', ['Mag1_Diurnal', 'Mag1_IGRF'])

    # ── Step 5: Heading correction ────────────────────────────────────────────
    if 5 in steps:
        print("\n── Step 5: Heading correction ───────────────────────────────────────")

        # Estimate bias from all selected lines combined
        parts_h = []
        for _, row in selected.iterrows():
            pq = interim_root / 'm02' / row['date'] / f"flight_{row['flight_id']}_m02.parquet"
            if not pq.exists():
                continue
            df  = pd.read_parquet(pq)
            seg = df[(df['line_id'] == row['line_id']) & df['line_valid']].copy()
            if not seg.empty:
                parts_h.append(seg)

        if not parts_h:
            print("  No segments loaded — skipping heading correction.")
        else:
            df_all_h = pd.concat(parts_h, ignore_index=True)

            if 'Mag1_IGRF' not in df_all_h.columns:
                print("  Mag1_IGRF not found — run step 4 first.")
            else:
                bias = estimate_heading_bias(df_all_h, col='Mag1_IGRF')

                for _, frow in flights.iterrows():
                    date = frow['date']
                    fid  = frow['flight_id']
                    pq   = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"
                    if not pq.exists():
                        continue
                    df_full = pd.read_parquet(pq)
                    df_out  = apply_heading(df_full, bias)
                    df_out.to_parquet(pq, index=False)
                    print(f"  Updated: {pq.relative_to(PROJECT_ROOT)}")

                export_step_output(selected, interim_root, out_root,
                                   '05_heading', ['Mag1_IGRF', 'Mag1_IGRF_head'])

    # ── Step 6: Sensor average ────────────────────────────────────────────────
    if 6 in steps:
        print("\n── Step 6: Sensor average ───────────────────────────────────────────")

        for _, frow in flights.iterrows():
            date = frow['date']
            fid  = frow['flight_id']
            pq   = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"

            if not pq.exists():
                print(f"  Skipping {date}/flight_{fid}: m02 parquet not found — run steps 1-5 first")
                continue

            df_full = pd.read_parquet(pq)

            if 'Mag1_IGRF_head' not in df_full.columns:
                print(f"  Skipping {date}/flight_{fid}: Mag1_IGRF_head not found — run step 5 first")
                continue

            df_out = apply_sensor_average(df_full)
            df_out.to_parquet(pq, index=False)
            print(f"  Updated: {pq.relative_to(PROJECT_ROOT)}")

        export_step_output(selected, interim_root, out_root,
                           '06_average', ['Mag1_IGRF_head', 'Mag2_IGRF_head', 'Mag_IGRF_head'])

    # ── Step 7: Tie-line levelling ────────────────────────────────────────────
    if 7 in steps:
        print("\n── Step 7: Tie-line levelling ───────────────────────────────────────")

        # Load all lines (production + tie) from all flights
        parts_lev = []
        for _, frow in flights.iterrows():
            pq = interim_root / 'm02' / frow['date'] / f"flight_{frow['flight_id']}_m02.parquet"
            if not pq.exists():
                continue
            df = pd.read_parquet(pq)
            on = df[df['line_id'].notna() & df['line_valid']].copy()
            if not on.empty:
                parts_lev.append(on)

        if not parts_lev:
            print("  No data loaded — skipping levelling.")
        else:
            df_all_lev = pd.concat(parts_lev, ignore_index=True)

            if 'Mag_IGRF_head' not in df_all_lev.columns:
                print("  Mag_IGRF_head not found — run step 6 first.")
            else:
                offsets = compute_crossover_offsets(df_all_lev, col='Mag_IGRF_head')

                for _, frow in flights.iterrows():
                    date = frow['date']
                    fid  = frow['flight_id']
                    pq   = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"
                    if not pq.exists():
                        continue
                    df_full = pd.read_parquet(pq)
                    df_out  = apply_levelling(df_full, offsets, col='Mag_IGRF_head')
                    df_out.to_parquet(pq, index=False)
                    print(f"  Updated: {pq.relative_to(PROJECT_ROOT)}")

                export_step_output(selected, interim_root, out_root,
                                   '07_levelling', ['Mag_IGRF_head', 'Mag_IGRF_head_level'])

    # ── Step 8: Micro-levelling ───────────────────────────────────────────────
    if 8 in steps:
        print("\n── Step 8: Micro-levelling ──────────────────────────────────────────")

        parts_ml = []
        for _, row in selected.iterrows():
            pq = interim_root / 'm02' / row['date'] / f"flight_{row['flight_id']}_m02.parquet"
            if not pq.exists():
                continue
            df  = pd.read_parquet(pq)
            seg = df[(df['line_id'] == row['line_id']) & df['line_valid']].copy()
            if not seg.empty:
                parts_ml.append(seg)

        if not parts_ml:
            print("  No data loaded — skipping micro-levelling.")
        else:
            df_all_ml = pd.concat(parts_ml, ignore_index=True)

            if 'Mag_IGRF_head_level' not in df_all_ml.columns:
                print("  Mag_IGRF_head_level not found — run step 7 first.")
            else:
                line_spacing_m = cfg['survey_design']['line_spacing_m']
                df_corrected   = apply_microlevelling(df_all_ml, line_spacing_m)

                # Write Mag_Final back to each flight parquet
                for (fid, lid), seg in df_corrected.groupby(['flight_id', 'line_id']):
                    # Find the date for this flight
                    date_rows = selected[selected['flight_id'] == fid]
                    if date_rows.empty:
                        continue
                    date = date_rows.iloc[0]['date']
                    pq   = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"
                    if not pq.exists():
                        continue
                    df_full = pd.read_parquet(pq)
                    df_full.loc[
                        df_full['line_id'] == lid, 'Mag_Final'
                    ] = seg['Mag_Final'].values
                    df_full.to_parquet(pq, index=False)

                print(f"  Mag_Final written to all flight parquets.")
                export_step_output(selected, interim_root, out_root,
                                   '08_microlevelling',
                                   ['Mag_IGRF_head_level', 'Mag_Final'])

    # ── Consolidated GeoPackage + map ─────────────────────────────────────────
    print("\n── Consolidated GeoPackage ─────────────────────────────────────────")
    export_geopackage(selected, interim_root, out_root / 'campaign_m02.gpkg')

    print("\n── Campaign map ────────────────────────────────────────────────────")
    plot_campaign_map(selected, interim_root, lag_result, out_root / 'campaign_m02_map.png')

    sep = '─' * 55
    print(f"\n{sep}")
    print(f"  GeoPackage  : outputs/{campaign}/{run_name}/m02/campaign_m02.gpkg")
    print(f"  Campaign map: outputs/{campaign}/{run_name}/m02/campaign_m02_map.png")
    print(f"{sep}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='M2 magnetic corrections')
    parser.add_argument('date', nargs='?', default=None,
                        help='Process one day only (DD.MM.YYYY)')
    parser.add_argument('--steps', default=None,
                        help='Comma-separated steps to run, e.g. 1,2 or 3 or 1,2,3')
    args = parser.parse_args()

    steps = None
    if args.steps:
        steps = {int(s.strip()) for s in args.steps.split(',')}
        # steps 1 and 2 are always together
        if 1 in steps or 2 in steps:
            steps |= {1, 2}

    main(target_date=args.date, steps=steps)
