"""
Module 0 — Export selected lines.

Reads line_selection.csv (rows where selected=True), pulls the corresponding
valid (line_valid=True) rows from the prepared parquets, and writes them out
in three formats for use outside this pipeline:

  1. GeoPackage — for visual QC in QGIS. 'selected_points' (every valid
     sample, all columns kept as attributes) and 'selected_lines' (one
     LineString per line), both carrying a `line_id` field so they can be
     styled/filtered per line.
  2. CSV        — every column present in the prepared parquet, one row per
     valid sample, for all selected segments combined.
  3. XYZ        — the same data as plain-text ASCII, formatted with 'Line'
     tags so Oasis Montaj's ASCII/XYZ import (File > Import > Data > ASCII)
     can load it straight into a new database. Geosoft's native binary .gdb
     format needs the proprietary Geosoft GX API (geosoft.gxpy), which in
     turn needs an Oasis Montaj installation/license, and isn't available in
     this environment — this text format is the portable equivalent Montaj
     reads natively, no plugin required on either side.

Usage:
    python -m src.m00_preparation.export_selected              # everything
    python -m src.m00_preparation.export_selected production   # line_id 1xxxx only
    python -m src.m00_preparation.export_selected tielines      # line_id 3xxxx only
"""

import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
import yaml
from shapely.geometry import LineString

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

CRS_WGS84 = 'EPSG:4326'


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def load_selected_data(interim_root: Path, line_type: str | None = None) -> pd.DataFrame:
    """
    Load valid rows for every (flight_id, line_id) marked selected=True in
    line_selection.csv, from the prepared parquets.

    line_type : None (everything), 'production' (line_id 1xxxx) or
                'tielines' (line_id 3xxxx) — matches TestSurveyNav.csv's own
                numbering convention (production lines E-W spaced 250 m,
                tie lines N-S spaced 1500 m).
    """
    sel_path = interim_root / 'line_selection.csv'
    if not sel_path.exists():
        raise FileNotFoundError(
            f"line_selection.csv not found at {sel_path}\n"
            "Run build_line_selection.py first."
        )
    selection = pd.read_csv(sel_path, dtype={'flight_id': str, 'line_id': int})
    selection = selection[selection['selected'] == True]
    if line_type == 'production':
        selection = selection[selection['line_id'] // 10000 == 1]
    elif line_type == 'tielines':
        selection = selection[selection['line_id'] // 10000 == 3]
    if selection.empty:
        raise ValueError("No rows are marked selected=True in line_selection.csv"
                          + (f" for line_type={line_type!r}" if line_type else ""))

    parts = []
    for _, row in selection.iterrows():
        pq_path = interim_root / 'm00' / row['date'] / f"flight_{row['flight_id']}_prepared.parquet"
        if not pq_path.exists():
            print(f"  Skipping {row['date']}/{row['flight_id']} line {row['line_id']}: parquet not found")
            continue
        df = pd.read_parquet(pq_path)
        seg = df[(df['line_id'] == row['line_id']) & df['line_valid']].copy()
        if seg.empty:
            print(f"  Skipping {row['date']}/{row['flight_id']} line {row['line_id']}: no valid rows")
            continue
        seg['date'] = row['date']
        parts.append(seg)
        print(f"  Loaded {row['date']}/{row['flight_id']} line {row['line_id']}  ({len(seg):,} rows)")

    if not parts:
        raise ValueError("No data loaded for any selected line — nothing to export.")
    return pd.concat(parts, ignore_index=True)


def _sanitise_for_gpkg(df: pd.DataFrame) -> pd.DataFrame:
    """Cast pandas nullable dtypes to plain types fiona can write to GeoPackage."""
    df = df.copy()
    if 'date' in df.columns:
        # 'date' holds the DD.MM.YYYY folder name as plain text; OGR tries to
        # interpret a field literally named 'date' as a Date type and fails
        # on that format, so it's renamed for the GIS output only.
        df = df.rename(columns={'date': 'flight_date'})
    if 'line_id' in df.columns:
        df['line_id'] = df['line_id'].astype(str).replace({'<NA>': '', 'nan': ''})
    for col in df.columns:
        if col == 'line_id':
            continue
        dtype = df[col].dtype
        if not pd.api.types.is_extension_array_dtype(dtype):
            continue
        if pd.api.types.is_numeric_dtype(dtype) or pd.api.types.is_bool_dtype(dtype):
            # nullable numeric/boolean (Int64, boolean, ...) -> plain float64
            df[col] = df[col].astype('float64')
        else:
            # text extension dtypes (e.g. string[pyarrow]) -> plain object/str
            df[col] = df[col].astype(object)
    return df


def build_points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Every valid sample as a Point, all columns kept as attributes."""
    valid = _sanitise_for_gpkg(df.dropna(subset=['Xgps', 'Ygps']))
    geometry = gpd.points_from_xy(valid['Xgps'], valid['Ygps'])
    return gpd.GeoDataFrame(valid.reset_index(drop=True), geometry=geometry, crs=CRS_WGS84)


def build_lines(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """One LineString per (flight_id, line_id, date) segment."""
    rows = []
    for (fid, lid, date), seg in df.groupby(['flight_id', 'line_id', 'date'], sort=False):
        seg_sorted = seg.dropna(subset=['Xgps', 'Ygps']).sort_values('M3clk')
        if len(seg_sorted) < 2:
            continue
        coords = list(zip(seg_sorted['Xgps'], seg_sorted['Ygps']))
        rows.append({
            'flight_id': fid,
            'line_id': int(lid),
            'flight_date': date,
            'n_points': len(seg_sorted),
            'ralt_mean': seg_sorted['Ralt'].mean() if 'Ralt' in seg_sorted.columns else None,
            'geometry': LineString(coords),
        })
    if not rows:
        return gpd.GeoDataFrame(
            columns=['flight_id', 'line_id', 'flight_date', 'n_points', 'ralt_mean', 'geometry'],
            geometry='geometry', crs=CRS_WGS84,
        )
    return gpd.GeoDataFrame(rows, crs=CRS_WGS84)


def write_xyz(df: pd.DataFrame, out_path: Path) -> None:
    """
    Write a Geosoft-style Line-tagged ASCII file that Oasis Montaj's
    File > Import > Data > ASCII/XYZ wizard reads directly into a database.

    Format: one header row of channel names, then for each (flight_id,
    line_id, date) segment a 'Line,<line_id>' tag row followed by its data
    rows, comma-delimited, sorted by M3clk (acquisition time).
    """
    cols = [c for c in df.columns if c != 'geometry']
    with open(out_path, 'w') as f:
        f.write(','.join(cols) + '\n')
        for (fid, lid, date), seg in df.groupby(['flight_id', 'line_id', 'date'], sort=True):
            seg_sorted = seg.sort_values('M3clk')
            f.write(f"Line,{lid}\n")
            seg_sorted[cols].to_csv(f, header=False, index=False, lineterminator='\n')
    print(f"Saved: {out_path}")


def export_selected(line_type: str | None = None) -> None:
    """
    line_type : None (default, everything), 'production' or 'tielines' — see
                load_selected_data(). Filtered runs get a filename suffix so
                they never overwrite the full export.
    """
    cfg = load_config()
    campaign = cfg['campaign']['name']
    run_name = cfg['campaign']['run_name']
    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
    out_dir = PROJECT_ROOT / 'outputs' / campaign / run_name / 'm00' / 'selected_export'
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f'_{line_type}' if line_type else ''

    print(f"Campaign  : {campaign}")
    print(f"Run       : {run_name}")
    print(f"Line type : {line_type or 'all (production + tielines)'}")
    print("Loading selected lines...")
    df = load_selected_data(interim_root, line_type)
    print(f"  {len(df):,} total valid rows across {df['line_id'].nunique()} lines")

    # ---- 1. GeoPackage -----------------------------------------------------
    gpkg_path = out_dir / f'{campaign}_selected{suffix}.gpkg'
    print("Building GeoPackage layers...")
    points = build_points(df)
    lines  = build_lines(df)
    points.to_file(gpkg_path, layer='selected_points', driver='GPKG')
    lines.to_file(gpkg_path, layer='selected_lines', driver='GPKG')
    print(f"Saved: {gpkg_path}  (layers: selected_points, selected_lines)")

    # ---- 2. CSV --------------------------------------------------------------
    csv_path = out_dir / f'{campaign}_selected{suffix}.csv'
    df.to_csv(csv_path, index=False)
    print(f"Saved: {csv_path}  ({len(df):,} rows)")

    # ---- 3. Oasis Montaj-compatible XYZ ---------------------------------------
    xyz_path = out_dir / f'{campaign}_selected{suffix}.xyz'
    write_xyz(df, xyz_path)


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    if arg not in (None, 'production', 'tielines'):
        print("Usage: python -m src.m00_preparation.export_selected [production|tielines]")
        sys.exit(1)
    export_selected(arg)
