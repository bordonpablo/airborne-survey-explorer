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
| `sync_sensors.py` | Internal — synchronises sensors with `merge_asof`, trims transients |

## Campaign selection

The active campaign is defined in `config/project.yaml`:

```yaml
campaign:
  name: "Mongolia_2022"
  raw_data_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022"
```

To process a different campaign, edit that file. No script arguments are needed.

## Execution flow

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
3. Trims the first and last 5 s of each survey line (transients)
4. Saves to `data/interim/<campaign>/<date>/flight_XXXXX_prepared.parquet`

### Step 2 — Verify in QGIS (optional)

```bash
python -m src.m00_preparation.export_qgis
```

Generates `outputs/<campaign>/verification_YYYYMMDD_HHMMSS.gpkg` with three layers:

- `survey_plan` — planned lines (UTM 48N)
- `flight_tracks` — actual GPS positions point by point
- `flight_lines` — each `(flight_id, line_id)` segment as a LineString

Each run produces a new timestamped file so multiple runs can be compared
against the same dataset.

## Outputs

| Path | Contents |
|---|---|
| `data/interim/<campaign>/<run_name>/config.yaml` | Snapshot of the config used — kept for reproducibility |
| `data/interim/<campaign>/<run_name>/<date>/flight_XXXXX_prepared.parquet` | Synchronised DataFrame, input for M01 |
| `outputs/<campaign>/<run_name>/verification_YYYYMMDD_HHMMSS.gpkg` | GeoPackage for QGIS verification |
