# Airborne Survey Explorer

Python pipeline for processing airborne geophysical data (magnetics and radiometry) acquired
by light aircraft. Covers the full processing chain from raw sensor files to corrected,
gridded products — implemented in modular, reusable code.

The reference campaign is **Mongolia 2022**. The pipeline is fully parametrised via
`config/project.yaml` and designed for reuse across future campaigns.

---

## Pipeline

| Module | Folder | Description |
|--------|--------|-------------|
| M0 — Preparation | `src/m00_preparation/` | File parsing, sensor synchronisation, line identification and trimming |
| M1 — QC | `src/m01_qc/` | Quality control: altitude, attitude, cross-track, speed, spacing, magnetic noise, diurnal |
| M2 — Magnetics | `src/m02_magnetics/` | GPS lag, diurnal, IGRF, heading, sensor average, levelling, micro-levelling → `Mag_Final` |
| M3 — Radiometry | `src/m03_radiometry/` | FSA corrections: dead-time, background, radon, altitude; concentrations |
| M4 — Gridding | `src/m04_gridding/` | Interpolation to 60 m grid; analytic signal, vertical derivative, tilt derivative → GeoTIFF |
| M5 — Export | `src/m05_export/` | Maps, profiles, GeoTIFF, Shapefile, final report |

---

## Project structure

```
airborne-survey-explorer/
├── config/
│   └── project.yaml                    ← active survey parameters (campaign, run_name, etc.)
├── data/                               ← never committed to git
│   ├── raw/Mongolia_2022/
│   │   └── Daten_Nisleg_2022/
│   │       ├── TestSurveyNav.csv       ← survey plan
│   │       └── <date>/                 ← raw flight files (GGA, MAG, SPC, Tagesgang)
│   ├── interim/
│   │   └── <campaign>/
│   │       └── <run_name>/             ← one folder per processing run
│   │           ├── config.yaml         ← config snapshot for reproducibility
│   │           ├── m00/<date>/         ← prepared parquets (M0)
│   │           ├── m02/<date>/         ← corrected parquets with Mag_Final (M2)
│   │           └── line_selection.csv  ← which lines enter M2 (edit manually)
│   └── processed/
├── outputs/
│   └── <campaign>/
│       └── <run_name>/
│           ├── m00/                    ← QGIS GeoPackages (M0)
│           ├── m01/                    ← QC reports (M1)
│           ├── m02/                    ← per-step GeoPackages and maps (M2)
│           ├── m04/                    ← GeoTIFF grids (M4)
│           └── reference/              ← specialist ground-truth
└── src/
    ├── m00_preparation/
    ├── m01_qc/
    ├── m02_magnetics/
    ├── m03_radiometry/
    ├── m04_gridding/
    ├── m05_export/
    └── utils/
```

---

## Setup

```powershell
python -m venv airborne-env
airborne-env\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Configuration

Edit `config/project.yaml` before running any module:

```yaml
campaign:
  name: "Mongolia_2022"              # campaign identifier, used in output paths
  run_name: "2022-04-24"             # processing variant label
  raw_data_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022"
  survey_nav_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022/TestSurveyNav.csv"
  start_date: "2022-04-24"
  center_area: [107.57, 47.81]       # lon, lat — for IGRF and map centering
  projection: "EPSG:32648"           # delivery CRS (WGS84 / UTM zone 48N)

survey_design:                       # flight plan geometry
  nominal_altitude_m: 100            # drape target in metres
  line_spacing_m: 250
  tieline_spacing_m: 1500
  line_direction_deg: 90             # 90 = E-W production lines

m1:                                  # QC thresholds
  line_tolerance_m: 300              # max cross-track deviation to accept a line

magnetics:
  igrf_base_field_nT: 59150          # regional IGRF field at the survey area
  igrf_model: "IGRF-13"

gridding:
  cell_size_m: 60
  method: "minimum_curvature"
```

---

## Data

Fixed-width ASCII files produced by the GeoDuster acquisition system.
One day may contain multiple flights; one flight may contain multiple survey lines.

| File | Rate | Content |
|------|------|---------|
| `GGA*` | ~10 Hz | Differential GPS navigation |
| `MAG*` | ~10 Hz | Magnetometers, radar altimeter, attitude (Roll/Pitch/Yaw) |
| `SPC*` | ~1 Hz | Gamma-ray spectrometer, VLF channels |
| `Tagesgang*` | ~0.3 Hz | Magnetic base station (diurnal variation) |
| `Cfg*.xml` | — | Acquisition system configuration snapshot |

Sensors are **always synchronised by timestamp** (M1clk/M2clk/M3clk), never by GPS coordinates.

---

## Usage

Each implemented module has its own `README.md` with detailed execution instructions,
script descriptions, and usage examples.

| Module | README |
|---|---|
| M0 — Data Preparation | [src/m00_preparation/README.md](src/m00_preparation/README.md) |
| M1 — Quality Control | [src/m01_qc/README.md](src/m01_qc/README.md) |
| M2 — Magnetics | [src/m02_magnetics/README.md](src/m02_magnetics/README.md) |
| M3 — Radiometry | [src/m03_radiometry/README.md](src/m03_radiometry/README.md) |
| M4 — Gridding | [src/m04_gridding/README.md](src/m04_gridding/README.md) |
| Reference data | [data/reference/README.md](data/reference/README.md) |
