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

All pass/fail thresholds (`RadarMin`, `RadarMax`, `CrossTrack`, `GroundSpeedMin`, `GroundSpeedMax`) come exclusively from `TestSurveyNav.csv`. No thresholds for this module are defined in `config/project.yaml`.

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
- `outputs/<campaign>/<run_name>/m01/<scope>_qc_report.csv`

### Detail mode — one line

```powershell
python -m src.m01_qc.run 22.04.2022 00427 10010
```

### Interactive viewer

```powershell
python -m src.m01_qc.viewer                    # toda la campaña
python -m src.m01_qc.viewer 24.04.2022 00428   # un vuelo específico
```

Requires `contextily` for the satellite basemap (`pip install contextily`).

---

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/m01/<scope>_qc_report.csv` | Per-line metrics and pass/fail |
| `outputs/<campaign>/<run_name>/m01/<date>/flight_X_line_Y_detail.png` | Detail view snapshot |

## After reviewing the report

Edit `line_selection.csv` and set `selected = False` for lines that fail QC and
should not enter Module 2. Lines that fail one metric but are the only option for
that `line_id` may still be kept with a note.
