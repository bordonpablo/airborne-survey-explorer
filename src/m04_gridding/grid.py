"""
Module 4 — Gridding.

Interpolates scattered flight-line data onto a regular grid using
scipy.interpolate.griddata (cubic method).

The cubic method uses a piecewise cubic interpolant over a Delaunay
triangulation. It is not true minimum-curvature (which minimises the
integral of the squared second derivative globally), but produces
smooth, geophysically acceptable grids for survey data at this scale.

Coordinate system
-----------------
Flight data arrives in WGS84 geographic coordinates (Xgps = lon, Ygps = lat).
Gridding is performed in the campaign projection (UTM 48N, EPSG:32648) so that
cell_size_m is meaningful and the grid is isotropic.

Outputs
-------
A numpy masked array (grid) in UTM coordinates, plus the grid extent and
transform needed to write a GeoTIFF.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from pyproj import Transformer
from scipy.interpolate import griddata


def load_mag_final(
    selected: pd.DataFrame,
    interim_root: Path,
    col: str = 'Mag_Final',
) -> pd.DataFrame:
    """
    Load the selected line data from m02 parquets and return a DataFrame
    with only the columns needed for gridding.

    Parameters
    ----------
    selected     : rows from line_selection.csv where selected=True
    interim_root : data/interim/<campaign>/<run_name>/
    col          : magnetic column to grid (default: Mag_Final)
    """
    parts = []
    for _, row in selected.iterrows():
        pq = interim_root / 'm02' / row['date'] / f"flight_{row['flight_id']}_m02.parquet"
        if not pq.exists():
            continue
        df  = pd.read_parquet(pq, columns=['flight_id', 'line_id', 'line_valid',
                                            'Xgps', 'Ygps'] + [col])
        seg = df[(df['line_id'] == row['line_id']) & df['line_valid']].copy()
        if not seg.empty:
            parts.append(seg)

    if not parts:
        raise ValueError("No data loaded from m02 parquets. Run M2 first.")

    df_all = pd.concat(parts, ignore_index=True)
    df_all = df_all.dropna(subset=['Xgps', 'Ygps', col])
    print(f"  Loaded {len(df_all):,} valid points from {len(parts)} segments")
    return df_all


def reproject_to_utm(
    df: pd.DataFrame,
    projection: str,
    col: str = 'Mag_Final',
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Reproject lon/lat to UTM and return (easting, northing, values).

    Parameters
    ----------
    projection : CRS string from project.yaml (e.g. 'EPSG:32648')
    """
    transformer = Transformer.from_crs('EPSG:4326', projection, always_xy=True)
    east, north = transformer.transform(df['Xgps'].values, df['Ygps'].values)
    values      = df[col].values.astype(float)
    return east, north, values


def make_grid(
    east: np.ndarray,
    north: np.ndarray,
    values: np.ndarray,
    cell_size_m: float,
    method: str = 'cubic',
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Interpolate scattered points onto a regular UTM grid.

    Parameters
    ----------
    east, north : UTM coordinates (m)
    values      : field values at each point
    cell_size_m : grid cell size in metres
    method      : scipy griddata method ('cubic', 'linear', 'nearest')

    Returns
    -------
    grid_e  : 1D array of easting coordinates (cell centres)
    grid_n  : 1D array of northing coordinates (cell centres)
    grid_z  : 2D masked array (rows = northing, cols = easting)
    extent  : dict with xmin, xmax, ymin, ymax, cell_size, shape, crs
    """
    xmin, xmax = east.min(),  east.max()
    ymin, ymax = north.min(), north.max()

    # Add a half-cell margin
    margin = cell_size_m / 2
    xmin -= margin; xmax += margin
    ymin -= margin; ymax += margin

    grid_e = np.arange(xmin, xmax + cell_size_m, cell_size_m)
    grid_n = np.arange(ymin, ymax + cell_size_m, cell_size_m)
    GE, GN = np.meshgrid(grid_e, grid_n)

    print(f"  Grid size    : {len(grid_e)} × {len(grid_n)} = {len(grid_e)*len(grid_n):,} cells")
    print(f"  Cell size    : {cell_size_m} m")
    print(f"  Extent E     : {xmin:.0f} – {xmax:.0f} m")
    print(f"  Extent N     : {ymin:.0f} – {ymax:.0f} m")
    print(f"  Interpolating ({method})...")

    points = np.column_stack([east, north])
    grid_z = griddata(points, values, (GE, GN), method=method)

    # Mask cells outside the convex hull (NaN from griddata)
    grid_z = np.ma.masked_invalid(grid_z)

    extent = {
        'xmin': xmin, 'xmax': xmax,
        'ymin': ymin, 'ymax': ymax,
        'cell_size': cell_size_m,
        'shape': grid_z.shape,
    }
    return grid_e, grid_n, grid_z, extent
