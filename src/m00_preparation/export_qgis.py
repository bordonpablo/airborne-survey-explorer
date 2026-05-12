"""
Module 0 — QGIS export.

Builds a GeoPackage with four layers for visual verification in QGIS, plus a
.qgs project file that loads them as a named group in the Layers panel.

  survey_plan   — planned survey lines from TestSurveyNav.csv (UTM 48N)
  flight_tracks — all GPS positions point by point, complete flight (WGS84)
  line_points   — valid on-line points only (line_valid=True), point by point (WGS84)
  flight_lines  — valid on-line segments as LineStrings (WGS84)

Output: outputs/<campaign>/<run_name>/verification[_date][_flight].gpkg + .qgs
Re-running with the same scope overwrites the previous file.

Usage:
    python -m src.m00_preparation.export_qgis
    python -m src.m00_preparation.export_qgis 22.04.2022
    python -m src.m00_preparation.export_qgis 22.04.2022 00447
"""

import io
import sys
import uuid
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from src.m00_preparation.read_survey_nav import read_survey_nav

CRS_WGS84 = 'EPSG:4326'
CRS_UTM48N = 'EPSG:32648'

TRACK_COLS = ['flight_id', 'line_id', 'line_valid', 'M3clk', 'time_s',
              'Xgps', 'Ygps', 'Ralt', 'Mag1', 'Mag2',
              'Roll', 'Pitch', 'Yaw', 'Sk', 'Su', 'Sth']

# (layer_name, geometry_type_str, geometry_type_int, crs)
_LAYERS = [
    ('survey_plan',   'Line',  1, CRS_UTM48N),
    ('flight_lines',  'Line',  1, CRS_WGS84),
    ('line_points',   'Point', 0, CRS_WGS84),
    ('flight_tracks', 'Point', 0, CRS_WGS84),
]


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
    return gpd.GeoDataFrame(nav, geometry=geometries, crs=CRS_UTM48N)


def load_parquets(
    interim_root: Path,
    target_date: str | None = None,
    target_flight: str | None = None,
) -> pd.DataFrame:
    """Load prepared parquet files, optionally filtered by date and flight."""
    if target_date and target_flight:
        candidates = [interim_root / target_date / f'flight_{target_flight}_prepared.parquet']
    elif target_date:
        candidates = sorted((interim_root / target_date).glob('flight_*_prepared.parquet'))
    else:
        candidates = sorted(interim_root.rglob('flight_*_prepared.parquet'))

    parts = []
    for pq in candidates:
        if not pq.exists():
            print(f"  Not found: {pq}")
            continue
        available = pd.read_parquet(pq).columns.tolist()
        cols = [c for c in TRACK_COLS if c in available]
        df = pd.read_parquet(pq, columns=cols)
        df['date'] = pq.parent.name
        parts.append(df)
        print(f"  Loaded {pq.parent.name}/{pq.name}  ({len(df):,} rows)")

    if not parts:
        raise FileNotFoundError(f"No parquet files found under {interim_root}")
    return pd.concat(parts, ignore_index=True)


def build_flight_tracks(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """All GPS points as a Point GeoDataFrame in WGS84 — complete flight."""
    valid = df.dropna(subset=['Xgps', 'Ygps'])
    geometry = gpd.points_from_xy(valid['Xgps'], valid['Ygps'])
    gdf = gpd.GeoDataFrame(valid.reset_index(drop=True), geometry=geometry, crs=CRS_WGS84)
    gdf['line_id'] = gdf['line_id'].astype(str).replace('<NA>', '')
    return gdf


def build_line_points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Valid on-line GPS points (line_valid=True) as a Point GeoDataFrame in WGS84."""
    mask = df['line_id'].notna()
    if 'line_valid' in df.columns:
        mask &= df['line_valid']
    valid = df[mask].dropna(subset=['Xgps', 'Ygps'])
    geometry = gpd.points_from_xy(valid['Xgps'], valid['Ygps'])
    gdf = gpd.GeoDataFrame(valid.reset_index(drop=True), geometry=geometry, crs=CRS_WGS84)
    gdf['line_id'] = gdf['line_id'].astype(str).replace('<NA>', '')
    return gdf


def build_flight_lines(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Each (flight_id, line_id) segment as a LineString in WGS84 — valid rows only."""
    valid = df['line_valid'] if 'line_valid' in df.columns else True
    on_line = df[df['line_id'].notna() & valid].copy()
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
            'mag1_mean': seg_sorted['Mag1'].mean() if 'Mag1' in seg_sorted.columns else None,
            'ralt_mean': seg_sorted['Ralt'].mean() if 'Ralt' in seg_sorted.columns else None,
            'geometry': LineString(coords),
        })
    return gpd.GeoDataFrame(rows, crs=CRS_WGS84)


def generate_qgis_project(gpkg_path: Path, group_name: str) -> Path:
    """
    Write a minimal QGIS project (.qgs) that loads the GeoPackage layers
    inside a named group in the Layers panel.

    The datasource paths are relative to the .qgs file, so the pair
    (.gpkg + .qgs) can be moved together without breaking links.
    """
    layer_ids = {name: str(uuid.uuid4()) for name, *_ in _LAYERS}
    gpkg_rel = f'./{gpkg_path.name}'

    root = Element('qgis', version='3.0.0')

    # --- Layer tree ---------------------------------------------------------
    tree_root = SubElement(root, 'layer-tree-group')
    SubElement(tree_root, 'custom-order', enabled='0')

    group = SubElement(tree_root, 'layer-tree-group',
                       name=group_name, checked='Qt::Checked', expanded='1')
    SubElement(group, 'custom-order', enabled='0')
    for name, *_ in _LAYERS:
        SubElement(group, 'layer-tree-layer',
                   id=layer_ids[name],
                   name=name,
                   checked='Qt::Checked',
                   expanded='1')

    # --- Project layers -----------------------------------------------------
    projectlayers = SubElement(root, 'projectlayers')
    for name, geom_str, geom_int, crs in _LAYERS:
        ml = SubElement(projectlayers, 'maplayer', type='vector', geometry=geom_str)
        SubElement(ml, 'id').text = layer_ids[name]
        SubElement(ml, 'datasource').text = f'{gpkg_rel}|layername={name}'
        SubElement(ml, 'layername').text = name
        SubElement(ml, 'provider', encoding='UTF-8').text = 'ogr'
        srs = SubElement(ml, 'srs')
        sr = SubElement(srs, 'spatialrefsys')
        SubElement(sr, 'authid').text = crs
        SubElement(ml, 'layerGeometryType').text = str(geom_int)

    # --- Write --------------------------------------------------------------
    project_path = gpkg_path.with_suffix('.qgs')
    et = ElementTree(root)
    indent(et, space='  ')
    buf = io.StringIO()
    et.write(buf, encoding='unicode', xml_declaration=False)
    content = "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n" + buf.getvalue()
    project_path.write_text(content, encoding='utf-8')
    return project_path


def export_gpkg(
    output_path: Path,
    target_date: str | None = None,
    target_flight: str | None = None,
) -> None:
    cfg = load_config()
    nav_path = PROJECT_ROOT / cfg['campaign']['survey_nav_path']
    interim_root = (PROJECT_ROOT / 'data' / 'interim'
                    / cfg['campaign']['name'] / cfg['campaign']['run_name'])

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("Building survey plan...")
    survey_plan = build_survey_plan(nav_path)
    print(f"  {len(survey_plan)} planned lines")

    print("Loading parquet files...")
    df = load_parquets(interim_root, target_date, target_flight)
    print(f"  {len(df):,} total rows")

    print("Building flight tracks...")
    tracks = build_flight_tracks(df)

    print("Building line points...")
    points = build_line_points(df)
    print(f"  {len(points):,} valid on-line points")

    print("Building flight lines...")
    lines = build_flight_lines(df)
    print(f"  {len(lines)} segments (flight × line_id)")

    print(f"Writing {output_path}...")
    survey_plan.to_file(output_path, layer='survey_plan', driver='GPKG')
    lines.to_file(output_path, layer='flight_lines', driver='GPKG')
    points.to_file(output_path, layer='line_points', driver='GPKG')
    tracks.to_file(output_path, layer='flight_tracks', driver='GPKG')

    scope = '_'.join(filter(None, [target_date, target_flight]))
    group_name = f"{cfg['campaign']['run_name']} — {scope}" if scope else cfg['campaign']['run_name']
    project_path = generate_qgis_project(output_path, group_name)

    print(f"\nDone.")
    print(f"  GeoPackage   : {output_path}")
    print(f"  QGIS project : {project_path}  ← open this in QGIS")
    print(f"  survey_plan  — {len(survey_plan)} planned lines  (UTM 48N)")
    print(f"  flight_tracks — {len(tracks):,} GPS points (complete flight)")
    print(f"  line_points  — {len(points):,} valid on-line points")
    print(f"  flight_lines — {len(lines)} flown segments")


if __name__ == '__main__':
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    flight_arg = sys.argv[2].zfill(5) if len(sys.argv) > 2 else None

    cfg = load_config()
    base = PROJECT_ROOT / 'outputs' / cfg['campaign']['name']
    if date_arg and flight_arg:
        out = base / date_arg / flight_arg / cfg['campaign']['run_name'] / 'verification.gpkg'
    elif date_arg:
        out = base / date_arg / cfg['campaign']['run_name'] / 'verification.gpkg'
    else:
        out = base / cfg['campaign']['run_name'] / 'verification.gpkg'

    export_gpkg(out, date_arg, flight_arg)
