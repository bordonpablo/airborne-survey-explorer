# Module 1 — Quality Control

Reads all selected (flight_id, line_id) segments from `line_selection.csv`,
computes QC metrics per segment, saves a report CSV, and opens a visualisation.

## Metrics computed

| Metric | Variable | What it measures |
|---|---|---|
| `ralt_mean_m` | Ralt | Mean radar altitude |
| `ralt_pct_outside` | Ralt | Fraction of points outside [RadarMin, RadarMax] |
| `lalt_mean_m` | Lalt | Mean laser altitude (if available) |
| `roll_max_deg` | Roll | Max \|Roll\| on the line |
| `roll_pct_outside` | Roll | Fraction with \|Roll\| > threshold |
| `pitch_max_deg` | Pitch | Max \|Pitch\| on the line |
| `pitch_pct_outside` | Pitch | Fraction with \|Pitch\| > threshold |
| `yaw_std_deg` | Yaw | Heading standard deviation (consistency) |
| `cross_track_max_m` | GPS vs plan | Max perpendicular distance from planned line |
| `cross_track_mean_m` | GPS vs plan | Mean perpendicular distance |
| `speed_mean_kmh` | GPS | Mean ground speed (computed from GPS positions) |
| `speed_pct_outside` | GPS | Fraction outside [SpeedMin, SpeedMax] |
| `gap_max_m` | GPS | Largest gap between consecutive points |
| `n_gaps` | GPS | Number of gaps exceeding threshold |
| `mag_noise_nT` | Mag1 | Noise level: std(Δ²Mag) / √6 |
| `mag_spike_count` | Mag1 | Number of isolated spikes above threshold |
| `diurnal_range_nT` | Tagesgang | Base-station variation during the line |

Altitude thresholds (RadarMin, RadarMax, SpeedMin, SpeedMax) are read from
`TestSurveyNav.csv`. All other thresholds are in `config/project.yaml` under `m1:`.

## Configuration

```yaml
m1:
  line_tolerance_m: 300        # max cross-track deviation (m)
  roll_max_deg: 5.0
  pitch_max_deg: 5.0
  yaw_std_max_deg: 10.0        # heading std dev limit
  gap_max_m: 200.0             # max GPS gap to pass spacing check
  pct_outside_max: 0.20        # max fraction of bad points to pass a metric
  mag_noise_max_nT: 5.0
  mag_spike_max_nT: 100.0
  diurnal_max_nT: 50.0
```

## Execution

**Prerequisite**: `line_selection.csv` must exist. Run `build_line_selection.py` first.

### Summary mode — all selected lines

```powershell
python -m src.m01_qc.run                          # all selected lines
python -m src.m01_qc.run 22.04.2022               # one day
python -m src.m01_qc.run 22.04.2022 00427         # one flight
```

Produces:
- Terminal table of pass/fail per metric per line
- `outputs/<campaign>/<run_name>/qc/<scope>_qc_report.csv`
- Interactive figure: GPS map (green = pass, red = fail) + metric heatmap

### Detail mode — one line with interactive slider

```powershell
python -m src.m01_qc.run 22.04.2022 00427 10010           # Ralt (default)
python -m src.m01_qc.run 22.04.2022 00427 10010 Roll      # Roll
python -m src.m01_qc.run 22.04.2022 00427 10010 Mag1      # Mag1
```

Opens a two-panel figure: GPS track (left) and variable profile (right).
A slider controls the threshold; points exceeding it turn red in both panels.

Available variables: `Ralt`, `Lalt`, `Roll`, `Pitch`, `Yaw`, `Mag1`, `Mag2`

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/qc/<scope>_qc_report.csv` | Per-line metrics and pass/fail |
| `outputs/<campaign>/<run_name>/qc/<scope>_qc_report.png` | Summary map + heatmap |
| `outputs/<campaign>/<run_name>/qc/<date>/flight_X_line_Y_<var>.png` | Detail view snapshot |

## After reviewing the report

Edit `line_selection.csv` and set `selected = False` for lines that fail QC and
should not enter Module 2. Lines that fail one metric but are the only option for
that `line_id` may still be kept with a note.
