# Airborne Survey Explorer

Python pipeline for processing airborne geophysical data (magnetics and radiometry) acquired
by light aircraft. Covers the full processing chain from raw sensor files to corrected,
gridded products — implemented in modular, reusable code.

The reference campaign is **Mongolia 2022**. The pipeline is fully parametrised via
`config/project.yaml` and designed for reuse across future campaigns.

---

## Pipeline

| Module | Folder | Description | Status |
|--------|--------|-------------|--------|
| M0 — Preparation | `src/m00_preparation/` | File parsing, sensor synchronisation, line identification and trimming | [complete](src/m00_preparation/README.md) |
| M1 — QC | `src/m01_qc/` | Quality control: altitude, spacing, magnetic noise, diurnal drift | planned |
| M2 — Magnetics | `src/m02_magnetics/` | Lag, diurnal, heading, IGRF corrections; levelling | planned |
| M3 — Radiometry | `src/m03_radiometry/` | FSA corrections: dead-time, background, radon, altitude; concentrations | planned |
| M4 — Gridding | `src/m04_gridding/` | Regular grid, magnetic and radiometric derived products | planned |
| M5 — Export | `src/m05_export/` | Maps, profiles, GeoTIFF, Shapefile, final report | planned |

---

## Project structure

```
airborne-survey-explorer/
├── config/
│   └── project.yaml                ← active survey parameters
├── data/
│   ├── raw/Mongolia_2022/
│   │   └── Daten_Nisleg_2022/
│   │       ├── TestSurveyNav.csv   ← survey plan (in git)
│   │       └── <date>/             ← raw flight data (ignored by git)
│   ├── interim/                    ← intermediate outputs (ignored by git)
│   └── processed/                  ← final processed data (ignored by git)
├── outputs/
│   └── <campaign>/             ← one subfolder per campaign, files with timestamp
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

## Configuration

All survey parameters are read from `config/project.yaml`. No paths or constants are
hardcoded in the scripts.

```yaml
campaign:
  name: "Mongolia_2022"
  raw_data_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022"
  projection: "EPSG:32648"    # WGS84 / UTM zone 48N

flight:
  nominal_altitude_m: 100
  line_spacing_m: 250
  line_direction_deg: 90      # E-W
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
