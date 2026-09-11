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
| `export_selected.py` | **Deliverable export.** GeoPackage, CSV and Oasis Montaj-ready XYZ for the selected lines. |
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
4. Filters points farther than `line_editing.turn_filter_m` (manual, `project.yaml`)
   from the planned line axis, also flagging them `line_valid = False`. This catches
   points where Wayp was armed too early/late — e.g. still near the airport, far off
   to the side of the line — that step 3 alone would miss because their along-track
   position still falls inside the planned extent. This is deliberately a separate,
   looser number from `CrossTrack` in `TestSurveyNav.csv` (M1's QC tolerance) — it
   only exists to drop gross outliers, not to enforce line-quality tolerance, so it
   won't discard points that are still legitimately part of the line but exceed the
   QC tolerance. Leave `turn_filter_m` unset in `project.yaml` to disable this step.
5. Saves to `data/interim/<campaign>/<run_name>/m00/<date>/flight_XXXXX_prepared.parquet`

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

Before committing to a selection, check whether each line was actually flown the
way it was planned:

```powershell
python -m src.m00_preparation.inspect_segment 22.04.2022                # every flight prepared for that day
python -m src.m00_preparation.inspect_segment 22.04.2022 00427          # all lines of one flight
python -m src.m00_preparation.inspect_segment 22.04.2022 00427 10010    # one specific line
```

Prints a summary table (n_points, mean altitude, altitude std) and saves one PNG
per line with six panels, all flight-plan compliance — nothing about sensor signal
quality, that's Module 1's job once a line is selected:

1. Radar altitude vs `RadarHeight`/`RadarMin`/`RadarMax`
2. Cross-track deviation vs `CrossTrack`
3. Ground speed vs `GroundSpeedMin`/`GroundSpeedMax`
4. Cross-angle deviation vs `CrossAngle`
5. Roll / Pitch
6. Yaw

All four thresholds in panels 1-4 are read live from `TestSurveyNav.csv` for
that line — nothing here comes from `config/project.yaml`. The title shows the
flight heading (arrow + compass point + bearing) so it's clear which direction
that pass was flown. No interactive window opens — figures are only saved to
`outputs/<campaign>/<run_name>/m00/<date>/inspection/` — a subfolder inside that
day's folder, so it doesn't mix with the `.gpkg`/`.qgs` files `export_qgis.py`
saves alongside it under `outputs/<campaign>/<run_name>/m00/<date>/`.

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

### Step 4 — Export selected lines (optional)

Exports the `selected=True` rows to `outputs/<campaign>/<run_name>/m00/selected_export/`:
a GeoPackage, a CSV, and a Line-tagged `.xyz` importable in Oasis Montaj.

```powershell
python -m src.m00_preparation.export_selected              # everything
python -m src.m00_preparation.export_selected production   # line_id 1xxxx only
python -m src.m00_preparation.export_selected tielines      # line_id 3xxxx only
```

Filtered runs get a filename suffix (`..._production.gpkg`, `..._tielines.gpkg`, ...)
so they don't overwrite the full export.

### Mixing flights from different run_names (manual)

Everything in M0/M1 resolves paths from a single `run_name` (`config/project.yaml`)
— `build_line_selection.py` and `m01_qc/run.py` only ever look inside that one
run's `m00/` folder. There's no built-in way to pull one flight's parquet from a
different run.

If a specific flight needs different parameters (e.g. a different
`line_editing.turn_filter_m`) than the rest of the campaign — because its real
navigation deviation doesn't fit the campaign-wide value and no other flight
covers that line more cleanly — the manual workaround is:

1. Temporarily set the parameter you need in `config/project.yaml` under a
   throwaway `run_name` (e.g. `test_002`) and run `prepare.py` for just that
   flight: `python -m src.m00_preparation.prepare <date> <flight_id>`.
2. Copy the resulting parquet into the real run's folder, overwriting the one
   generated with the campaign-wide config:
   `data/interim/<campaign>/<real_run_name>/m00/<date>/flight_<flight_id>_prepared.parquet`
3. **Leave a note in that run's interim folder** recording which flight was
   swapped in, from which throwaway run, with which parameter value, and why —
   otherwise the flight silently stops matching the `config.yaml` snapshot
   already saved there, and there's no other record of the exception. `data/interim/`
   isn't tracked by git, so this note only lives locally; write it anyway, it's
   for future-you.
4. Re-running `prepare.py` for the whole campaign on the real run will
   overwrite your manual copy back to the campaign-wide config — redo the copy
   afterwards if that happens.

### Viewing a parquet without QGIS

```powershell
python -c "import pandas as pd; df = pd.read_parquet('data/interim/Mongolia_2022/full_campaign/m00/22.04.2022/flight_00447_prepared.parquet'); print(df.shape); print(df.head(10))"
```

The **Parquet Explorer** extension in VS Code can also browse `.parquet` files directly.

---

## Outputs

| Path | Contents |
|---|---|
| `data/interim/<campaign>/<run_name>/config.yaml` | Config snapshot for reproducibility |
| `data/interim/<campaign>/<run_name>/m00/<date>/flight_XXXXX_prepared.parquet` | Synchronised DataFrame, one per flight |
| `data/interim/<campaign>/<run_name>/line_selection.csv` | Line selection table — input for M1 |
| `outputs/<campaign>/[<date>/[<flight_id>/]]<run_name>/<scope>.gpkg` | GeoPackage for QGIS verification |
| `outputs/<campaign>/<run_name>/m00/<date>/inspection/flight_X_line_Y.png` | Sensor profile plots per line |
| `outputs/<campaign>/<run_name>/m00/selected_export/<campaign>_selected.{gpkg,csv,xyz}` | Selected-lines deliverables (GIS, CSV, Oasis Montaj) |
