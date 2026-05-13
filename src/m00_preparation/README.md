# Module 0 — Data Preparation

Reads raw files for each flight (MAG, GGA, SPC), synchronises sensors by timestamp,
clips each survey line to its planned extent, and saves the result as a Parquet file.
Also provides tools for visual verification in QGIS and for building the line selection
table that feeds into M1.

## Scripts

| Script | Role |
|---|---|
| `prepare.py` | **Main entry point.** Processes one or all flights. |
| `export_qgis.py` | **Visual verification.** Generates a GeoPackage for QGIS. |
| `build_line_selection.py` | **M0 → M1 bridge.** Builds `line_selection.csv` from processed parquets. |
| `inspect_segment.py` | **Segment inspection.** Plots altitude, magnetics and attitude for a flight or line. |
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
  run_name: "full_campaign"           # controls which subfolder results are saved to
  raw_data_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022"
```

---

## Execution

### Step 1 — Prepare flights

Process the entire active campaign (all days and all flights):

```powershell
python -m src.m00_preparation.prepare
```

Process a single day:

```powershell
python -m src.m00_preparation.prepare 22.04.2022
```

Process a single flight from a specific day:

```powershell
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

### Step 2 — Verify in QGIS

```powershell
python -m src.m00_preparation.export_qgis                    # all processed days
python -m src.m00_preparation.export_qgis 22.04.2022         # one day
python -m src.m00_preparation.export_qgis 22.04.2022 00447   # one flight
```

Output paths depend on the scope:
- All days: `outputs/<campaign>/<run_name>/<campaign>.gpkg`
- Single day: `outputs/<campaign>/<date>/<run_name>/<date>.gpkg`
- Single flight: `outputs/<campaign>/<date>/<flight_id>/<run_name>/<flight_id>.gpkg`

Each file contains four layers:
- `survey_plan` — planned lines from TestSurveyNav.csv (UTM 48N)
- `flight_tracks` — all GPS positions point by point, complete flight (WGS84)
- `line_points` — valid on-line points only (`line_valid = True`), point by point (WGS84)
- `flight_lines` — each `(flight_id, line_id)` segment as a LineString, valid rows only (WGS84)

### Step 2b — Inspect a segment (optional)

Before committing to a selection, plot the sensor profiles for any flight or line:

```powershell
python -m src.m00_preparation.inspect_segment 22.04.2022 00447         # all lines of a flight
python -m src.m00_preparation.inspect_segment 22.04.2022 00447 1001    # one specific line
```

Prints a summary table (n_points, mean altitude, altitude std, magnetic range) and
opens one figure per line with three panels: radar altitude, Mag1/Mag2, Roll/Pitch.
Figures are also saved as PNG to `outputs/<campaign>/<run_name>/inspection/<date>/`.

### Step 3 — Build line selection (M0 → M1 bridge)

After inspecting flights in QGIS and/or with `inspect_segment`, run:

```powershell
python -m src.m00_preparation.build_line_selection                     # all flights
python -m src.m00_preparation.build_line_selection 22.04.2022          # one day
python -m src.m00_preparation.build_line_selection 22.04.2022 00447    # one flight
```

This scans the prepared parquets and writes (or updates):
`data/interim/<campaign>/<run_name>/line_selection.csv`

| Column | Description |
|---|---|
| `line_id` | Survey line number |
| `flight_id` | Which flight covers this line |
| `date` | Flight date folder |
| `n_valid_points` | Valid on-line points in this segment |
| `selected` | `True` = enters M1; `False` = skip |

When the same `line_id` was flown in multiple flights, the script auto-selects
the one with the most valid points. **Edit `selected` manually** in the CSV to
override any automatic choice. Re-running the script after adding new flights
preserves existing manual edits.

### Viewing a parquet without QGIS

```powershell
python -c "import pandas as pd; df = pd.read_parquet('data/interim/Mongolia_2022/full_campaign/22.04.2022/flight_00447_prepared.parquet'); print(df.shape); print(df.head(10))"
```

The **Parquet Explorer** extension in VS Code can also browse `.parquet` files directly.

---

## Outputs

| Path | Contents |
|---|---|
| `data/interim/<campaign>/<run_name>/config.yaml` | Config snapshot for reproducibility |
| `data/interim/<campaign>/<run_name>/<date>/flight_XXXXX_prepared.parquet` | Synchronised DataFrame, one per flight |
| `data/interim/<campaign>/<run_name>/line_selection.csv` | Line selection table — input for M1 |
| `outputs/<campaign>/[<date>/[<flight_id>/]]<run_name>/<scope>.gpkg` | GeoPackage for QGIS verification |
| `outputs/<campaign>/<run_name>/inspection/<date>/flight_X_line_Y.png` | Sensor profile plots per line |
