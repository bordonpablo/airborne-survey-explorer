# Module 0 — Data Preparation

Reads raw files for each flight (MAG, GGA, SPC), synchronises sensors by timestamp,
and saves the result as a Parquet file ready for M01.

## Scripts

| Script | Role |
|---|---|
| `prepare.py` | **Main entry point.** Processes one or all flights. |
| `export_qgis.py` | **Visual verification.** Generates a GeoPackage for QGIS. |
| `read_mag.py` | Internal — parses MAG files (~10 Hz, magnetometer + attitude) |
| `read_gga.py` | Internal — parses GGA files (~10 Hz, differential GPS) |
| `read_spc.py` | Internal — parses SPC files (~1 Hz, spectrometer) |
| `read_tagesgang.py` | Internal — parses magnetic base station files |
| `read_survey_nav.py` | Internal — reads `TestSurveyNav.csv` (planned lines) |
| `sync_sensors.py` | Internal — synchronises sensors with `merge_asof`, clips to planned line extents |

---

## Configuration

The active campaign and processing run are defined in `config/project.yaml`:

```yaml
campaign:
  name: "Mongolia_2022"
  run_name: "clip_extent_01"         # controls which subfolder results are saved to
  raw_data_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022"
```

To process a different campaign or isolate a processing variant, edit `run_name` before
running. All outputs go to `data/interim/<name>/<run_name>/` and
`outputs/<name>/<run_name>/`.

---

## Execution

### Step 1 — Prepare flights

Process the entire active campaign (all days and all flights):

```bash
python -m src.m00_preparation.prepare
```

Process a single day:

```bash
python -m src.m00_preparation.prepare 22.04.2022
```

Process a single flight from a specific day:

```bash
python -m src.m00_preparation.prepare 22.04.2022 00427
```

The date argument must match the folder name exactly (format `DD.MM.YYYY`).
The flight ID is the 5-digit number from the corresponding MAG file
(e.g. `MAG00427.txt` → `00427`).

For each processed flight the script:
1. Reads MAG, GGA and SPC files
2. Synchronises the three sensors onto the GGA time axis (`merge_asof`)
3. Clips each survey line to its planned A→B extent using along-track projection
   (points outside the planned start/end are flagged `line_valid = False`)
4. Saves to `data/interim/<campaign>/<run_name>/<date>/flight_XXXXX_prepared.parquet`

A snapshot of the active `project.yaml` is saved to `data/interim/<campaign>/<run_name>/config.yaml`
at the start of each run so that results are always reproducible.

### Step 2 — Verify in QGIS (optional)

```bash
python -m src.m00_preparation.export_qgis                    # all processed days
python -m src.m00_preparation.export_qgis 22.04.2022         # one day
python -m src.m00_preparation.export_qgis 22.04.2022 00447   # one flight
```

The campaign and run are read from `project.yaml` — no extra arguments needed.
Output paths depend on the scope:
- All days: `outputs/<campaign>/<run_name>/<campaign>.gpkg`
- Single day: `outputs/<campaign>/<date>/<run_name>/<date>.gpkg`
- Single flight: `outputs/<campaign>/<date>/<flight_id>/<run_name>/<flight_id>.gpkg`

Each file contains four layers:
- `survey_plan` — planned lines from TestSurveyNav.csv (UTM 48N)
- `flight_tracks` — all GPS positions point by point, complete flight (WGS84)
- `line_points` — valid on-line points only (`line_valid = True`), point by point (WGS84)
- `flight_lines` — each `(flight_id, line_id)` segment as a LineString, valid rows only (WGS84)

A `.qgs` project file is written alongside the `.gpkg` — open it in QGIS to load all layers
already grouped and named.

### Viewing the parquet output

To quickly inspect a prepared file without QGIS:

```powershell
python -c "import pandas as pd; df = pd.read_parquet('data/interim/Mongolia_2022/clip_extent_01/22.04.2022/flight_00447_prepared.parquet'); print(df.shape); print(df.head(10))"
```

Alternatively, install the **Parquet Explorer** extension in VS Code to browse files directly.

---

## Outputs

| Path | Contents |
|---|---|
| `data/interim/<campaign>/<run_name>/config.yaml` | Config snapshot — kept for reproducibility |
| `data/interim/<campaign>/<run_name>/<date>/flight_XXXXX_prepared.parquet` | Synchronised DataFrame, input for M01 |
| `outputs/<campaign>/[<date>/[<flight_id>/]]<run_name>/<scope>.gpkg` | GeoPackage for QGIS verification |
| `outputs/<campaign>/[<date>/[<flight_id>/]]<run_name>/<scope>.qgs` | QGIS project file (open this in QGIS) |
