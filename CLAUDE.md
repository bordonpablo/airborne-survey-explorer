# CLAUDE.md — Project: airborne-survey-explorer

This file gives Claude Code the context, structure, and conventions of this project.
Read it in full before generating any code or modifying any file.

---

## What this project does

Python tool for processing airborne geophysical data (magnetics and radiometry) acquired
by light aircraft. Implements the full geophysical processing chain — from raw sensor files
to corrected grids and maps — in custom, modular, and reusable code.

The reference campaign is **Mongolia 2022**. The design is reusable for future campaigns
by parameterising everything through `config/project.yaml`.

---

## Data structure

### Raw data — inside the repository but ignored by git

Raw flight data lives in `data/raw/Mongolia_2022/Daten_Nisleg_2022/` organised by flight day.
These folders are listed in `.gitignore` and **are never committed to git**.
Only `TestSurveyNav.csv` is versioned because it is small and is survey configuration.

```
data/raw/Mongolia_2022/
└── Daten_Nisleg_2022/
    ├── TestSurveyNav.csv       ← in git (survey plan, treated as configuration)
    ├── 22.04.2022/             ← not in git (raw flight data)
    │   ├── GGA00447            # GPS navigation, flight 447
    │   ├── MAG00447            # Magnetometer, flight 447
    │   ├── SPC00447            # Spectrometer, flight 447
    │   ├── EVT00447            # Event log, flight 447
    │   ├── Cfg00447            # System configuration, flight 447
    │   ├── GGA00451            # (same for flight 451)
    │   ├── MAG00451
    │   ├── SPC00451
    │   ├── EVT00451
    │   ├── Cfg00451
    │   ├── Tagesgang00447_00451   # Magnetic base station (covers the full day)
    │   └── Flugbuch               # Flight log with operator notes
    ├── 24.04.2022/
    └── ... (one directory per flight day)
```

One day may contain multiple flights. The number in the file name identifies the flight.
One flight may contain multiple survey lines.

### File types and key columns

| File       | Timestamp      | Rate    | Main columns |
|------------|----------------|---------|--------------|
| GGA        | M3clk (ms)     | ~10 Hz  | Xdgps, Ydgps, Zdgps, dWayp |
| MAG        | M1clk (ms)     | ~10 Hz  | Xgps, Ygps, Ralt, Lalt, Mag1, Mag2, Roll, Pitch, Yaw |
| SPC        | M2clk (ms)     | ~1 Hz   | Sxgps, Sygps, Sralt, Sk, Su, Sth, Sa0, Sa1, Sa2, Srate |
| Tagesgang  | time (HHMMSS)  | ~0.3 Hz | nT |
| SurveyNav  | —              | —       | line_id, x_start, y_start, x_end, y_end |

**Synchronisation**: M1clk / M2clk / M3clk are milliseconds since acquisition system start-up.
They are the synchronisation axis between sensors.
**Never synchronise sensors by GPS coordinates — always by timestamp.**

---

## Repository structure

```
airborne-survey-explorer/
├── CLAUDE.md                       ← this file
├── README.md
├── .gitignore
├── requirements.txt
├── config/
│   └── project.yaml                # Active survey parameters
├── data/
│   ├── raw/
│   │   └── Mongolia_2022/
│   │       └── Daten_Nisleg_2022/
│   │           ├── TestSurveyNav.csv   ← in git
│   │           ├── 22.04.2022/         ← ignored by git
│   │           └── ...
│   ├── interim/                    ← ignored by git
│   └── processed/                  ← ignored by git
├── docs/
├── img/
├── outputs/
│   └── <campaign>/             ← subcarpeta por campaña, archivos con timestamp
├── src/
│   ├── m00_preparation/
│   ├── m01_qc/
│   ├── m02_magnetics/
│   ├── m03_radiometry/
│   ├── m04_gridding/
│   ├── m05_export/
│   └── utils/
└── requirements.txt
```

---

## Processing pipeline

The order is strict. Each module receives the output of the previous one.
QC (M1) always comes after line editing (M0) because its metrics only make sense
over valid line segments, not over the full flight.

### Module 0 — Data preparation
**Input**: raw files for one flight (GGA, MAG, SPC, Tagesgang).
**Steps**:
- 0.1 Read and parse each file type with type-specific functions
- 0.2 Synchronise sensors by timestamp using `merge_asof()` (GGA as the primary axis)
- 0.3 Assign line ID from the `Wayp` field in MAG (populated in real-time by the onboard navigation
  system; blank = not on a survey line). Add `flight_id` from the filename (e.g. `"00427"` from
  `MAG00427.txt`). The unique segment key is `(flight_id, line_id)`. Repeated lines across days
  share the same `line_id` but have different `flight_id` values; the better segment is chosen
  during M1 QC.
- 0.4 Trim the first and last N seconds of each `(flight_id, line_id)` segment to remove
  alignment and pull-out transients.

**Output**: `data/interim/Mongolia_2022/<date>/flight_<N>_prepared.parquet`
DataFrame where every valid row has `flight_id` and `line_id` assigned and all sensors synchronised.
Rows with blank `Wayp` (transits, turns) are retained but flagged with `line_id = NaN`.

### Module 1 — Quality control (QC)
**Input**: prepared DataFrame from M0 (valid line data only).
**Steps**:
- Altitude deviation from the 100 m drape target
- Cross-track deviation from planned lines
- Sample spacing and gap detection
- Magnetic noise assessment per line
- Diurnal drift test against base station

**Output**: same DataFrame + flag columns (`flag_altitude`, `flag_spacing`, `flag_noise`)
+ report in `outputs/reports/`.

### Module 2 — Magnetic processing
**Input**: DataFrame with `line_id` and QC flags.
**Sequence**:
1. GNSS lag correction
2. Diurnal correction (Tagesgang)
3. Heading correction
4. Average of the two magnetometers
5. IGRF removal (IGRF-13 model)
6. Levelling with tie lines
7. Micro-levelling (decorrugation)

**Output**: column `Mag_Final` (Residual Magnetic Anomaly) added to the DataFrame.

### Module 3 — Radiometric processing
**Input**: same DataFrame.
**Sequence** (Medusa spectrometer FSA):
1. Dead-time correction
2. Aircraft background subtraction
3. Radon correction
4. Altitude correction (normalisation to STP)
5. Conversion to concentrations: K (%), eU (ppm), eTh (ppm)
6. Levelling and micro-levelling

**Output**: columns `K_corr`, `eU_corr`, `eTh_corr` added to the DataFrame.

### Module 4 — Gridding and derived products
**Input**: processed DataFrame from M2 and M3.
**Steps**:
- Interpolation to a regular grid (minimum curvature or kriging), cell ~50-60 m
- Magnetic products: RTP, analytic signal, vertical derivative, tilt derivative
- Radiometric products: ternary map K-eTh-eU, ratios, Dose Rate

**Output**: GeoTIFF grids in `outputs/maps/`.

### Module 5 — Visualisation and export
**Output**: maps, profiles, GeoTIFF, Shapefile, processed CSV, final report.

---

## config/project.yaml

```yaml
campaign:
  name: "Mongolia_2022"
  raw_data_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022"
  survey_nav_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022/TestSurveyNav.csv"
  start_date: "2022-04-22"
  center_area: [107.57, 47.81]       # lon, lat
  projection: "EPSG:32648"           # WGS84 / UTM zone 48N

flight:
  nominal_altitude_m: 100
  line_spacing_m: 250
  tieline_spacing_m: 1500
  line_direction_deg: 90             # E-W
  line_tolerance_m: 300              # For line identification

magnetics:
  igrf_base_field_nT: 59150
  igrf_model: "IGRF-13"

gridding:
  cell_size_m: 60
  method: "minimum_curvature"
```

Never hardcode paths or parameters in the code. Always read them from this file using pyyaml.

---

## Coding conventions

- `snake_case` for all variables and functions
- One file per sub-task: `read_gga.py`, `diurnal_correction.py`, `igrf_removal.py`
- Docstrings explaining what the function does AND the geophysical concept behind it
- `print()` with progress messages at each important step
- Save intermediates to `data/interim/` after each module
- Preferred formats: `.parquet` for large DataFrames, `.csv` for small tables

---

## Instructions for Claude Code

- Before generating code, briefly explain the geophysical concept involved
- If there is a formula, show it and explain each term
- Always include an example of how to run the script from the terminal
- Clearly indicate which parameters come from `project.yaml`
- Prefer solutions the user can run step by step
- When relevant, mention how the same step would be done in Oasis Montaj

---

## Reference campaign: Mongolia 2022

- Area: central Mongolia (~107.57°E, 47.81°N)
- Flight days: 22/04/2022 to 14/05/2022 (with gaps)
- Delivery projection: WGS84/UTM-48N (EPSG:32648)
- Production lines: E-W direction, 250 m spacing
- Tie lines: N-S direction, 1500 m spacing
- Nominal flight altitude: 100 m above terrain (drape)
- Kilometres flown: ~2263 km of production (of 2368 planned)
- IGRF reference field: 59150 nT
