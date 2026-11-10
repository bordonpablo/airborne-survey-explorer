# Module 2 — Magnetic corrections

Applies the chain of magnetic corrections to the selected survey lines. Starts from the
compensated field (`Mag1C` / `Mag2C`) delivered by M0 and ends in `Mag_Final`
(Residual Magnetic Anomaly).

Concepts, formulas and column names: [docs/m02_correction_chain.md](../../docs/m02_correction_chain.md).
Results and problems found in the campaign: [docs/findings_m02.md](../../docs/findings_m02.md).

---

## Steps

| Step | Script | What it does | Output column(s) | What each output column is |
|---|---|---|---|---|
| 0 | `inspect_raw.py` | Visual inspection of the raw columns (no correction) | — | — |
| 1 | `lag.py` | Estimate GPS–magnetometer lag | — (report only) | — |
| 2 | `lag.py` | Apply the lag correction if it is significant | `lag_applied` | Whether the GPS shift was applied (True/False) |
| 3 | `diurnal.py`, `diurnal_report.py` | Subtract the base-station diurnal variation | `BaseMag`, `Diurnal`, `Mag1_Diurnal`, `Mag2_Diurnal`, `utc_s` | `BaseMag`: field measured by the base station at that instant (nT). `Diurnal`: correction to add = reference − `BaseMag`. `Mag1_Diurnal` / `Mag2_Diurnal`: `Mag1C` / `Mag2C` + `Diurnal`. `utc_s`: UTC time of the sample (s since 1970-01-01) |
| 4 | `igrf.py` | Remove the IGRF-13 reference field | `IGRF`, `Mag1_IGRF`, `Mag2_IGRF` | `IGRF`: main field of the model at the sample (nT). `Mag1_IGRF` / `Mag2_IGRF`: `Mag1_Diurnal` / `Mag2_Diurnal` − `IGRF`, the residual anomaly |
| 5 | `heading.py` | Heading correction | `Mag1_IGRF_head`, `Mag2_IGRF_head` | `Mag1_IGRF` / `Mag2_IGRF` after the heading correction |
| 6 | `average_sensors.py` | Combine Mag1 and Mag2 | `Mag_IGRF_head`, `sensor_used` | `Mag_IGRF_head`: the two sensors combined into one. `sensor_used`: which sensor(s) went into it |
| 7 | `levelling.py` | Tie-line levelling | `Mag_IGRF_head_level` | `Mag_IGRF_head` after removing the line-to-line offsets |
| 8 | `microlevelling.py` | Micro-levelling | `Mag_Final` | `Mag_IGRF_head_level` after removing the along-line corrugation: the residual magnetic anomaly |

`run.py` is the entry point: it reads `line_selection.csv` and runs the steps.

### Steps 1–2 (GPS lag)

- The magnetometer reports each value slightly late, so anomalies end up shifted along the line. Step 1 measures that shift on lines flown in both directions; step 2 corrects it only if it is larger than the tolerance (`lag_tolerable_s`, a quarter of the line spacing).
- `lag_summary.txt` and `lag_report.json` give the measured lag and the decision: `LAG_NEGLIGIBLE` (nothing changed), `LAG_SIGNIFICANT` (GPS positions shifted) or `LAG_UNKNOWN` (no lines in both directions).
- `lag_applied` marks whether the shift was applied. No magnetic column changes in these steps.

### Columns of step 3

- `BaseMag`: field measured by the ground base station (nT), interpolated to the time of each airborne sample. Time series, not a map.
- `Diurnal`: correction to add (nT) = `diurnal_reference_nT − BaseMag`. It is the daily variation with the sign changed.
- `Mag1_Diurnal`, `Mag2_Diurnal`: `Mag1C` / `Mag2C` + `Diurnal`.

`diurnal_reference_nT` in `project.yaml` is the fixed reference level of the correction. The base station has a raw
curve and a filtered one (moving average, `base_filter_window_s`); `base_station_use` (`raw` or `filtered`) chooses
which one is subtracted, and `diurnal_base_station.png` draws both. Where a flight has no recording of its own, a
supplementary table (`base_station_supplement`, built by `base_supplement.py`) can fill it; those readings are drawn
in red.

---

## Run

```powershell
python -m src.m02_magnetics.inspect_raw            # step 0, whole campaign
python -m src.m02_magnetics.inspect_raw 22.04.2022 00447 1001   # one line
python -m src.m02_magnetics.run --steps 1,2        # lag
python -m src.m02_magnetics.run --steps 3          # diurnal (needs 1,2)
python -m src.m02_magnetics.run --steps 4          # ... and so on up to 8
```

Parameters come from `config/project.yaml` (`magnetics`, `campaign`).

---

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/m02/inspection/` | Step 0: per-line PNGs, campaign maps, GeoPackage |
| `outputs/<campaign>/<run_name>/m02/step_01_02_lag/` | `lag_summary.txt` (start here), `lag_report.json`, diagnosis plots |
| `outputs/<campaign>/<run_name>/m02/step_03_diurnal/` | `diurnal_summary.txt` (start here), base-station plot (raw and filtered) and table, correction-vs-time plot, field maps (Mag1, Mag2 and their mean, before and after), map of the correction at each point |
| `outputs/<campaign>/<run_name>/m02/step_<NN>_<name>/` | One GeoPackage and one map per later step |
| `data/interim/<campaign>/<run_name>/m02/<date>/flight_XXXXX_m02.parquet` | Per-flight data, columns added step by step |

Every step writes a `*_summary.txt` in plain language: read that first.
