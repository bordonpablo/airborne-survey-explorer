# Module 1 — Quality Control

Checks **how the aircraft flew** each selected line against the thresholds in
`TestSurveyNav.csv` (altitude, distance off line, speed). It does not judge the
geophysical sensors: magnetometer and spectrometer quality is looked at in
Module 2 / 3.

Prerequisite: `line_selection.csv` (Module 0, step 3).

## Workflow

1. Scan everything:

   ```powershell
   python -m src.m01_qc.run
   ```

   One day: `... run 22.04.2022`; one flight: `... run 22.04.2022 00427`.
   Prints a pass/fail table and saves `outputs/<campaign>/<run_name>/m01/qc_report.csv`.

2. Look closer at a failed line:

   ```powershell
   python -m src.m01_qc.run 22.04.2022 00427 10010
   ```

   6-panel snapshot: GPS track, altitude, Roll/Pitch, Yaw, Mag1/Mag2 (noise/spike
   readout), SPC and VLF (red when a channel looks flat or missing). Informational
   only: it does not affect pass/fail.

3. Decide: set `selected = False` in `line_selection.csv` for lines that should
   not enter Module 2. A failed line that is the only flight for its `line_id`
   can be kept; note why.

## Pass/fail

| Flag | Data used | Passes when... | Threshold |
|---|---|---|---|
| `pass_altitude` | `Ralt` (in feet in the raw data, converted to m) | mean within `[RadarMin, RadarMax]` | 82.3 – 100.6 m |
| `pass_cross_track` | `Xgps`, `Ygps` | max deviation from planned line ≤ `CrossTrack` | 25 m |
| `pass_speed` | `Xgps`, `Ygps`, `M3clk` | mean within `[GroundSpeedMin, GroundSpeedMax]` | 110 – 130 km/h |
| `pass_all` | | all three pass | |

Thresholds come only from `TestSurveyNav.csv`, never from `project.yaml`.

M0's `turn_filter_m` is a different, looser check: it only decides whether a point
belongs to the line. `pass_cross_track` is the real tolerance, applied to the whole line.

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/m01/qc_report.csv` (or `<date>_qc_report.csv` / `<date>_<flight>_qc_report.csv` for a narrower scan) | One row per line: `ralt_mean_m`, `cross_track_max_m`, `speed_mean_kmh`, and the 4 pass/fail flags |
| `outputs/<campaign>/<run_name>/m01/<date>/flight_X_line_Y_detail.png` | Detail snapshot from step 2 |
