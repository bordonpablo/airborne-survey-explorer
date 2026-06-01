# Module 4 — Gridding and magnetic derivative products

Interpolates the Residual Magnetic Anomaly (`Mag_Final`) from scattered flight-line
points onto a regular UTM grid, then computes standard magnetic derivative products.

## Scripts

| Script | Role |
|---|---|
| `run.py` | **Main entry point.** Loads m02 data, grids, exports GeoTIFFs and quick-look map. |
| `grid.py` | Data loading, UTM reprojection, scipy gridding. |
| `derivatives.py` | Analytic signal, vertical derivative, tilt derivative (FFT domain). |

---

## Parameters (project.yaml)

```yaml
campaign:
  projection: "EPSG:32648"    # output CRS — gridding in metres

gridding:
  cell_size_m: 60             # grid cell size
  method: "minimum_curvature" # mapped to scipy 'cubic' — closest equivalent
```

---

## Usage

```powershell
python -m src.m04_gridding.run
```

---

## Outputs (`outputs/<campaign>/<run_name>/m04/`)

| File | Contents |
|---|---|
| `Mag_Final.tif` | Residual Magnetic Anomaly grid (nT), GeoTIFF EPSG:32648 |
| `rtp.tif` | Reduction to Pole (nT) |
| `analytic_signal.tif` | Analytic signal amplitude (nT/m) |
| `horizontal_gradient.tif` | Horizontal gradient magnitude (nT/m) |
| `vertical_derivative.tif` | First vertical derivative (nT/m) |
| `tilt_derivative.tif` | Tilt derivative (degrees, ±90°) |
| `Mag_products_map.png` | Six-panel quick-look map |

---

## Gridding method

Uses `scipy.interpolate.griddata` with `method='cubic'` (piecewise cubic over
Delaunay triangulation). This is the closest available Python equivalent to
minimum curvature. For production-grade minimum curvature, GMT (`surface`) is
the standard tool.

## Derivative products

All derivatives are computed in the wavenumber (FFT) domain:

| Product | Formula | Use |
|---|---|---|
| RTP | Stabilised phase filter (Blakely 1995) | Reposition anomalies over sources |
| Analytic signal | `sqrt((dB/dx)² + (dB/dy)² + (dB/dz)²)` | Body edges, contacts |
| Horizontal gradient | `sqrt((dB/dx)² + (dB/dy)²)` | Contacts and faults |
| Vertical derivative | `dB/dz` | Enhance shallow sources |
| Tilt derivative | `atan(dB/dz / HGM)` | Geological contacts |

Inclination and declination for RTP are computed automatically from IGRF-13
at the survey centre (`campaign.center_area`) and start date (`campaign.start_date`).
