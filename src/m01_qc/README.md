# Module 1 — Quality Control

Reads the selected lines from `line_selection.csv`, checks each one against the
3 thresholds defined in `TestSurveyNav.csv`, and saves a pass/fail report. You
then look closer at any line that failed before deciding what enters Module 2.

**Prerequisite**: `line_selection.csv` must already exist (Module 0, step 3).

Like M0, everything here resolves paths from a single `run_name`
(`config/project.yaml`) — see `src/m00_preparation/README.md` ("Mixing flights
from different run_names") if a flight you need was prepared under a
different run.

---

## Workflow

**1. Scan everything**

```powershell
python -m src.m01_qc.run
```

Prints a pass/fail table to the console and saves the full report to
`outputs/<campaign>/<run_name>/m01/qc_report.csv`. Narrow the scan with
`python -m src.m01_qc.run 22.04.2022` (one day) or `... 22.04.2022 00427` (one flight).

**2. Look closer at a line that failed**

```powershell
python -m src.m01_qc.run 22.04.2022 00427 10010
```

Pops up and saves a 6-panel snapshot for that line — this is the "is the
recorded signal any good" view (M0's `inspect_segment` already answered "was
it flown correctly"): GPS track, altitude (vs `RadarMin`/`RadarMax`),
Roll/Pitch, Yaw, Mag1/Mag2 (with a noise/spike readout), and radiometric
(Sk/Su/Sth) and VLF panels that flag in red when a channel looks flat or
missing — usually a sign that sensor wasn't actually recording on this line.
None of this drives pass/fail (no TestSurveyNav threshold exists for it) —
it's here so you can eyeball what's going on. If SPC or VLF look dead, the
same warning is also printed to the console, not just drawn on the panel.

**3. Decide**

Edit `line_selection.csv` and set `selected = False` for lines that fail QC and
shouldn't enter Module 2. A line that fails one metric but is the *only* flight
covering that `line_id` can still be kept — just note why.

---

## What "pass/fail" means

These are the only 3 metrics computed — the ones `TestSurveyNav.csv` actually
defines a threshold for. Nothing else is checked automatically.

| Flag | Passes when... |
|---|---|
| `pass_altitude` | mean radar altitude is within `[RadarMin, RadarMax]` |
| `pass_cross_track` | max deviation from the planned line ≤ `CrossTrack` |
| `pass_speed` | mean ground speed is within `[SpeedMin, SpeedMax]` |
| `pass_all` | all three above pass |

Thresholds come **only** from `TestSurveyNav.csv` — never from `config/project.yaml`.
`pass_all` is what the console table and `line_selection.csv` decisions hinge on.

**Not the same check as M0's `turn_filter_m`.** Module 0 (`config/project.yaml`,
`line_editing.turn_filter_m`) only screens gross outliers — points hundreds/
thousands of metres off the planned line (e.g. Wayp armed near the airport) —
so a point can pass M0 and still fail here. `pass_cross_track` is the real,
much stricter campaign spec (`CrossTrack` in `TestSurveyNav.csv`, e.g. 25 m),
checked against the *whole selected line*, not per point. A line can have
every point `line_valid=True` in M0 and still fail `pass_cross_track` in M1 —
that's expected, it's what this module is for.

---

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/m01/qc_report.csv` (or `<date>_qc_report.csv` / `<date>_<flight>_qc_report.csv` for a narrower scan) | One row per line: `ralt_mean_m`, `cross_track_max_m`, `speed_mean_kmh`, and the 4 pass/fail flags |
| `outputs/<campaign>/<run_name>/m01/<date>/flight_X_line_Y_detail.png` | Step-2 snapshot, generated automatically when you run detail mode |
