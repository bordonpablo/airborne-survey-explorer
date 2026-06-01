"""
Module 4 — Gridding and derived magnetic products.

Reads Mag_Final from all selected m02 parquets, reprojects to UTM,
interpolates to a regular grid, exports GeoTIFFs, and computes
standard magnetic derivative products.

Input:
    data/interim/<campaign>/<run_name>/line_selection.csv
    data/interim/<campaign>/<run_name>/m02/<date>/flight_XXXXX_m02.parquet

Output (all in outputs/<campaign>/<run_name>/m04/):
    Mag_Final.tif               — Residual Magnetic Anomaly grid
    analytic_signal.tif         — Analytic signal amplitude
    vertical_derivative.tif     — First vertical derivative
    tilt_derivative.tif         — Tilt derivative (degrees)
    Mag_Final_map.png           — Quick-look map of all products

Parameters from project.yaml:
    campaign.projection         — output CRS (e.g. EPSG:32648)
    gridding.cell_size_m        — grid cell size in metres
    gridding.method             — 'cubic', 'linear', or 'nearest'

Usage:
    python -m src.m04_gridding.run
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import rasterio
from rasterio.transform import from_bounds
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m04_gridding.grid import load_mag_final, reproject_to_utm, make_grid
from src.m04_gridding.derivatives import compute_derivatives, field_direction


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def load_line_selection(interim_root: Path) -> pd.DataFrame:
    path = interim_root / 'line_selection.csv'
    if not path.exists():
        raise FileNotFoundError(f"line_selection.csv not found: {path}")
    return pd.read_csv(path, dtype={'flight_id': str, 'line_id': int})


def write_geotiff(
    grid_z: np.ndarray,
    extent: dict,
    out_path: Path,
    crs: str,
    nodata: float = -9999.0,
) -> None:
    """Write a 2D masked array to a single-band GeoTIFF."""
    data = np.where(np.ma.getmaskarray(grid_z), nodata, np.array(grid_z))
    transform = from_bounds(
        extent['xmin'], extent['ymin'],
        extent['xmax'], extent['ymax'],
        data.shape[1], data.shape[0],
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        out_path, 'w',
        driver='GTiff',
        height=data.shape[0], width=data.shape[1],
        count=1, dtype='float32',
        crs=crs, transform=transform,
        nodata=nodata,
        compress='lzw',
    ) as dst:
        dst.write(data.astype('float32'), 1)
    print(f"  Saved: {out_path.relative_to(PROJECT_ROOT)}")


def plot_quicklook(
    grid_e: np.ndarray,
    grid_n: np.ndarray,
    grids: dict[str, np.ndarray],
    out_path: Path,
) -> None:
    """Six-panel quick-look map of all gridded products."""
    titles = {
        'Mag_Final':           'Residual Magnetic Anomaly (nT)',
        'rtp':                 'Reduction to Pole (nT)',
        'analytic_signal':     'Analytic Signal (nT/m)',
        'horizontal_gradient': 'Horizontal Gradient (nT/m)',
        'vertical_derivative': 'Vertical Derivative (nT/m)',
        'tilt_derivative':     'Tilt Derivative (°)',
    }
    cmaps = {
        'Mag_Final':           'RdBu_r',
        'rtp':                 'RdBu_r',
        'analytic_signal':     'hot_r',
        'horizontal_gradient': 'hot_r',
        'vertical_derivative': 'RdBu_r',
        'tilt_derivative':     'RdBu_r',
    }

    available = {k: v for k, v in titles.items() if k in grids}
    n    = len(available)
    ncols = 3
    nrows = (n + ncols - 1) // ncols

    E, N = np.meshgrid(grid_e / 1000, grid_n / 1000)
    fig, axes = plt.subplots(nrows, ncols, figsize=(8 * ncols, 7 * nrows))
    axes_flat = np.array(axes).flatten()
    titles = available   # reuse variable

    for ax, (key, title) in zip(axes_flat, titles.items()):
        z = grids.get(key)
        if z is None:
            ax.set_visible(False)
            continue
        cmap = cmaps.get(key, 'RdBu_r')
        data = np.ma.filled(z, np.nan)
        p2, p98 = np.nanpercentile(data[~np.isnan(data)], [2, 98])
        sym_keys = {'Mag_Final', 'rtp', 'vertical_derivative', 'tilt_derivative'}
        if key in sym_keys:
            vabs = max(abs(p2), abs(p98))
            vmin, vmax = -vabs, vabs
        else:
            vmin, vmax = p2, p98

        im = ax.pcolormesh(E, N, data, cmap=cmap,
                           vmin=vmin, vmax=vmax, shading='auto', rasterized=True)
        plt.colorbar(im, ax=ax, shrink=0.8, label=title.split('(')[-1].rstrip(')'))
        ax.set_title(title, fontsize=10)
        ax.set_xlabel('Easting (km)', fontsize=8)
        ax.set_ylabel('Northing (km)', fontsize=8)
        ax.set_aspect('equal')
        ax.tick_params(labelsize=7)

    fig.suptitle('Module 4 — Magnetic gridded products', fontsize=12)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Quick-look: {out_path.relative_to(PROJECT_ROOT)}")


def main() -> None:
    cfg          = load_config()
    campaign     = cfg['campaign']['name']
    run_name     = cfg['campaign']['run_name']
    projection   = cfg['campaign']['projection']
    cell_size_m  = cfg['gridding']['cell_size_m']
    method       = cfg['gridding'].get('method', 'cubic')
    # scipy method mapping
    if method == 'minimum_curvature':
        method = 'cubic'

    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
    out_root     = PROJECT_ROOT / 'outputs' / campaign / run_name / 'm04'
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"Campaign   : {campaign}")
    print(f"Run        : {run_name}")
    print(f"Projection : {projection}")
    print(f"Cell size  : {cell_size_m} m")
    print(f"Method     : {method} (scipy.griddata)")

    # ── Load data ─────────────────────────────────────────────────────────────
    print("\n── Loading Mag_Final from m02 parquets ─────────────────────────────")
    line_sel = load_line_selection(interim_root)
    selected = line_sel[line_sel['selected'] == True].copy()
    df       = load_mag_final(selected, interim_root, col='Mag_Final')

    # ── Reproject and grid ────────────────────────────────────────────────────
    print("\n── Reprojecting and gridding ────────────────────────────────────────")
    east, north, values = reproject_to_utm(df, projection, col='Mag_Final')
    grid_e, grid_n, grid_z, extent = make_grid(east, north, values,
                                                cell_size_m, method=method)

    # ── Compute derivatives ───────────────────────────────────────────────────
    print("\n── Computing derivative products ────────────────────────────────────")
    lon_c, lat_c   = cfg['campaign']['center_area']
    start_date     = cfg['campaign']['start_date']   # YYYY-MM-DD
    y, mo, d       = [int(x) for x in start_date.split('-')]
    inc_deg, dec_deg = field_direction(lon_c, lat_c, 0.1, y, mo, d)
    derivs = compute_derivatives(grid_z, cell_size_m, inc_deg, dec_deg)

    # ── Export GeoTIFFs ───────────────────────────────────────────────────────
    print("\n── Exporting GeoTIFFs ───────────────────────────────────────────────")
    all_grids = {'Mag_Final': grid_z, **derivs}
    for name, grid in all_grids.items():
        write_geotiff(grid, extent, out_root / f'{name}.tif', crs=projection)

    # ── Quick-look map ────────────────────────────────────────────────────────
    print("\n── Quick-look map ───────────────────────────────────────────────────")
    plot_quicklook(grid_e, grid_n, all_grids, out_root / 'Mag_products_map.png')

    sep = '─' * 55
    print(f"\n{sep}")
    print(f"  M4 complete.")
    print(f"  Output: outputs/{campaign}/{run_name}/m04/")
    print(f"  GeoTIFFs: Mag_Final.tif, rtp.tif")
    print(f"            analytic_signal.tif, horizontal_gradient.tif")
    print(f"            vertical_derivative.tif, tilt_derivative.tif")
    print(f"{sep}")


if __name__ == '__main__':
    main()
