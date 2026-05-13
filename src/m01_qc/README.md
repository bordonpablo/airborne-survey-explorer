# Module 1 — Quality Control

Reads all selected (flight_id, line_id) segments from `line_selection.csv`,
computes QC metrics per segment, saves a report CSV, and opens a visualisation.

## Scripts

| Script | Role |
|---|---|
| `run.py` | **Main entry point.** Batch QC: summary map + metric heatmap, or detail view for one line. |
| `viewer.py` | **Interactive viewer.** Click a flight line on the map to inspect live profile panels (altitude, Roll/Pitch, Yaw, magnetics). |
| `metrics.py` | Internal — computes all QC metrics per segment. |
| `viz.py` | Internal — summary figure (map + heatmap) and detail figure (multi-panel profiles). |

---

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

### Detail mode — one line, all variables simultaneously

```powershell
python -m src.m01_qc.run 22.04.2022 00427 10010
```

Opens a multi-panel figure with all QC variables at once:
- GPS track map
- Radar altitude (with RadarMin/RadarMax reference lines)
- Roll + Pitch (with ±threshold lines)
- Yaw (heading consistency)
- Mag1 + Mag2

All profile panels share the along-track x-axis.

### Interactive viewer — one flight, click to inspect

```powershell
python -m src.m01_qc.viewer 24.04.2022 00428
```

Opens a window with two columns:

**Left — satellite map** (requires `contextily`):
- All survey lines for the flight are drawn on top of an Esri WorldImagery basemap.
- Lines are coloured **green** (pass) / **red** (fail) if a QC report exists for that
  flight, or **blue** when no report is available.
  Run `python -m src.m01_qc.run <date> <flight>` first to generate the report.
- The currently selected line is highlighted in **orange**.
- Click any line to select it and update the profiles.

**Right — four stacked profile panels** (all share the along-track x-axis):
1. Radar altitude (Ralt/Lalt) with RadarMin/RadarMax reference lines and
   mean altitude + fraction-outside annotation.
2. Roll + Pitch with ±threshold lines; fraction-outside annotation per channel.
3. Yaw with heading standard-deviation annotation.
4. Mag1 + Mag2 with spike markers (orange dots) and noise / spike-count
   annotations. Cross-track deviation, speed and gap count are shown at
   the right edge of this panel.

All annotations show the metric value and a ✓/✗ symbol matched to the
thresholds in `config/project.yaml` (`m1:` section) and `TestSurveyNav.csv`.

---

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
