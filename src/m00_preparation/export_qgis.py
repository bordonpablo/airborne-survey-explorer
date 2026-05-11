"""
Module 0 — QGIS export.

Builds a single GeoPackage with three layers for visual verification in QGIS:

  survey_plan   — planned survey lines from TestSurveyNav.csv (UTM 48N)
  flight_tracks — actual GPS positions for every processed flight, coloured by
                  flight_id and line_id; includes Mag1, Ralt, Roll, Pitch, Yaw
  flight_lines  — each (flight_id, line_id) segment as a LineString (lighter layer)

Output path: outputs/<campaign>/verification_YYYYMMDD_HHMMSS.gpkg
Each run produces a new timestamped file, so multiple processing runs can be compared.

Usage:
    python -m src.m00_preparation.export_qgis
    python -m src.m00_preparation.export_qgis outputs/Mongolia_2022/my_run.gpkg
"""

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from src.m00_preparation.read_survey_nav import read_survey_nav

CRS_WGS84 = 'EPSG:4326'
CRS_UTM48N = 'EPSG:32648'

# Columns to include in the flight_tracks layer (keeps file size manageable)
TRACK_COLS = ['flight_id', 'line_id', 'M3clk', 'time_s',
              'Xgps', 'Ygps', 'Ralt', 'Mag1', 'Mag2',
              'Roll', 'Pitch', 'Yaw', 'Sk', 'Su', 'Sth']


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def build_survey_plan(nav_path: Path) -> gpd.GeoDataFrame:
    """Planned survey lines as LineStrings in UTM 48N."""
    nav = read_survey_nav(nav_path)
    geometries = [
        LineString([(row.E_start, row.N_start), (row.E_end, row.N_end)])
        for _, row in nav.iterrows()
    ]
    gdf = gpd.GeoDataFrame(nav, geometry=geometries, crs=CRS_UTM48N)
    return gdf


def load_all_parquets(interim_root: Path) -> pd.DataFrame:
    """Load all prepared parquet files into a single DataFrame."""
    parts = []
    for pq in sorted(interim_root.rglob('flight_*_prepared.parquet')):
        df = pd.read_parquet(pq, columns=[c for c in TRACK_COLS
                                           if c in pd.read_parquet(pq, columns=[]).columns
                                           or True])
        # read only available columns
        available = pd.read_parquet(pq).columns.tolist()
        cols = [c for c in TRACK_COLS if c in available]
        df = pd.read_parquet(pq, columns=cols)
        df['date'] = pq.parent.name
        parts.append(df)
        print(f"  Loaded {pq.parent.name}/{pq.name}  ({len(df):,} rows)")
    return pd.concat(parts, ignore_index=True)


def build_flight_tracks(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """All GPS points as a Point GeoDataFrame in WGS84."""
    valid = df.dropna(subset=['Xgps', 'Ygps'])
    geometry = gpd.points_from_xy(valid['Xgps'], valid['Ygps'])
    gdf = gpd.GeoDataFrame(valid.reset_index(drop=True), geometry=geometry, crs=CRS_WGS84)
    # line_id as string for QGIS styling (nullable int causes issues in some QGIS versions)
    gdf['line_id'] = gdf['line_id'].astype(str).replace('<NA>', '')
    return gdf


def build_flight_lines(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Each (flight_id, line_id) segment as a LineString in WGS84."""
    on_line = df[df['line_id'].notna()].copy()
    rows = []
    for (fid, lid, date), seg in on_line.groupby(['flight_id', 'line_id', 'date'], sort=False):
        seg_sorted = seg.dropna(subset=['Xgps', 'Ygps']).sort_values('M3clk')
        if len(seg_sorted) < 2:
            continue
        coords = list(zip(seg_sorted['Xgps'], seg_sorted['Ygps']))
        rows.append({
            'flight_id': fid,
            'line_id': int(lid),
            'date': date,
            'n_points': len(seg_sorted),
            'mag1_mean': seg_sorted['Mag1'].mean() if 'Mag1' in seg_sorted else None,
            'ralt_mean': seg_sorted['Ralt'].mean() if 'Ralt' in seg_sorted else None,
            'geometry': LineString(coords),
        })
    return gpd.GeoDataFrame(rows, crs=CRS_WGS84)


def export_gpkg(output_path: Path) -> None:
    cfg = load_config()
    nav_path = PROJECT_ROOT / cfg['campaign']['survey_nav_path']
    interim_root = PROJECT_ROOT / 'data' / 'interim' / cfg['campaign']['name'] / cfg['campaign']['run_name']

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Building survey plan...")
    survey_plan = build_survey_plan(nav_path)
    print(f"  {len(survey_plan)} planned lines")

    print("Loading parquet files...")
    df = load_all_parquets(interim_root)
    print(f"  {len(df):,} total rows across all flights")

    print("Building flight tracks...")
    tracks = build_flight_tracks(df)

    print("Building flight lines...")
    lines = build_flight_lines(df)
    print(f"  {len(lines)} segments (flight × line_id)")

    print(f"Writing {output_path}...")
    survey_plan.to_file(output_path, layer='survey_plan', driver='GPKG')
    tracks.to_file(output_path, layer='flight_tracks', driver='GPKG')
    lines.to_file(output_path, layer='flight_lines', driver='GPKG')

    print(f"\nDone. Load in QGIS: {output_path}")
    print("\nLayers:")
    print(f"  survey_plan   — {len(survey_plan)} planned lines  (UTM 48N)")
    print(f"  flight_tracks — {len(tracks):,} GPS points      (WGS84)")
    print(f"  flight_lines  — {len(lines)} flown segments  (WGS84)")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    else:
        cfg = load_config()
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        out = PROJECT_ROOT / 'outputs' / cfg['campaign']['name'] / cfg['campaign']['run_name'] / f'verification_{ts}.gpkg'
    export_gpkg(out)
