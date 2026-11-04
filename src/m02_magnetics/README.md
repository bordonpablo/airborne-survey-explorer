# Module 2 — Magnetic Corrections

Applies the full chain of magnetic corrections to all selected survey lines,
starting from the compensated field (Mag1C / Mag2C) delivered by M0 and producing
the Residual Magnetic Anomaly (column `Mag_Final`).

For a plain-language explanation of the correction order and column names
see [docs/m02_correction_chain.md](../../docs/m02_correction_chain.md).

---

## Scripts

| Script | Role |
|---|---|
| `run.py` | **Main entry point.** Reads `line_selection.csv` and runs steps 1–8 (all, or `--steps 1,2`, `--steps 3`, ...). |
| `inspect_raw.py` | **Raw inspection.** Five-panel PNG per line before any correction. |
| `lag.py` | **GPS lag estimation and correction.** Cross-correlation of opposite-direction pairs. |
| `diurnal.py` | Diurnal correction (base station subtraction). |
| `igrf.py` | **IGRF-13 removal.** Computes and subtracts IGRF total field at each sample point using ppigrf. |
| `heading.py` | **Heading correction.** Empirical DC offset per heading direction (E/W). No calibration flight required. |
| `average_sensors.py` | **Sensor average.** Combines Mag1 and Mag2 using fourth-difference noise criterion. |
| `levelling.py` | **Tie-line levelling.** Crossover-based DC offset per production line. See docstring for eastern-edge limitation. |
| `microlevelling.py` | **Micro-levelling.** Along-line minus across-line moving average — removes residual corrugation, produces `Mag_Final`. |

---

## Correction order

The columns each step creates are listed below and explained in
[docs/m02_correction_chain.md](../../docs/m02_correction_chain.md).
The chain starts from `Mag1C` / `Mag2C` (compensated in flight). Step 0 is only an inspection, not a correction.

| Step | Script | Description | Output column(s) |
|---|---|---|---|
| 0 | `inspect_raw.py` | Visual inspection of the columns the aircraft delivers, before any correction | — |
| 1 | `lag.py` | Estimate GPS–magnetometer lag by cross-correlation of E/W line pairs | — (report only) |
| 2 | `lag.py` | Apply lag correction (only if decision = LAG_SIGNIFICANT). Shifts the GPS positions; no magnetic column changes | `Xgps`, `Ygps`, `Zgps` (shifted), `lag_applied` |
| 3 | `diurnal.py` | Subtract base-station diurnal variation interpolated to flight time | `Mag1_Diurnal`, `Mag2_Diurnal` |
| 4 | `igrf.py` | ✅ Remove IGRF-13 reference field (ppigrf, input: lon, lat, alt km, UTC date) | `Mag1_IGRF`, `Mag2_IGRF` |
| 5 | `heading.py` | ✅ Empirical heading correction — DC offset estimated from mean difference between E and W lines | `Mag1_IGRF_head`, `Mag2_IGRF_head` |
| 6 | `average_sensors.py` | ✅ Combine Mag1 and Mag2 — plain average; only the quieter sensor if the other is > 2× noisier (4th-difference noise test) | `Mag_IGRF_head`, `sensor_used` |
| 7 | `levelling.py` | ✅ Crossover DC offset per production line (tie lines as reference). Eastern edge limited by 5 missing ties. | `Mag_IGRF_head_level` |
| 8 | `microlevelling.py` | ✅ Along-line minus across-line smooth — corrugation removed | `Mag_Final` |

---

## Execution

### Step 0 — Inspect raw signal

```powershell
# All selected lines across the entire campaign (reads line_selection.csv)
python -m src.m02_magnetics.inspect_raw

# All lines of one day
python -m src.m02_magnetics.inspect_raw 22.04.2022

# All lines of one flight
python -m src.m02_magnetics.inspect_raw 22.04.2022 00447

# One specific line
python -m src.m02_magnetics.inspect_raw 22.04.2022 00447 1001

# Only the campaign-wide maps and GeoPackage (no per-line PNGs)
python -m src.m02_magnetics.inspect_raw maps
```

Produces the following outputs (all under `outputs/<campaign>/<run_name>/m02/inspection/`):

| File | Scope | Contents |
|---|---|---|
| `<date>/flight_X_line_Y.png` | per line | 5-panel profile (total field, gradient, 4th difference, attitude, altimetry) |
| `<date>/flight_X_summary.png` | per flight | Panel 1 thumbnails for all lines |
| `campaign_field_maps.png` | **whole campaign** | Scatter maps in lon/lat, one row per group sharing one colour scale (blue = low, red = high): total field (`Mag1`, `Mag2`, `Mag1C`, `Mag2C`), gradients (`MagL`, `MagLC`), 4th differences (`Mag1D`, `Mag2D`) |
| `maps/campaign_map_<column>.png` | **whole campaign** | The same maps, one image per column (`Mag1`, `Mag2`, `Mag1C`, `Mag2C`, `MagL`, `MagLC`, `Mag1D`, `Mag2D`); maps of one group keep the same colour scale |
| `campaign_raw.gpkg` | **whole campaign** | GeoPackage (EPSG:4326) — one layer per column, all selected lines |

The consolidated map and GeoPackage are only generated when running without arguments or with `maps` (whole-campaign mode). At M2 stage, line selection is already decided — the consolidated view is what matters.

**Panels and columns shown:**

| Panel | Columns | Description |
|---|---|---|
| 1 — Total field | `Mag1`, `Mag1C`, `Mag2`, `Mag2C` | Raw vs compensated for each sensor. `Mag1C`/`Mag2C` = aircraft interference removed by the onboard compensation system during flight. |
| 2 — Gradient | `MagL`, `MagLC` | `MagL` = `(Mag1 − Mag2) / 10.56`, the raw gradient between the two wingtip sensors, 10.56 m apart (nT/m). `MagLC` = compensated gradient (nT/m). |
| 3 — 4th difference | `Mag1D`, `Mag2D` | 4th difference of `Mag1` and `Mag2` as recorded by the system: the noise of each sensor along the line. Plotted as recorded, not recomputed. |
| 4 — Attitude | `Roll`, `Pitch`, `Yaw` | Aircraft orientation. Used to diagnose heading-dependent noise. |
| 5 — Altimetry | `Ralt`, `Lalt` | Radar altimeter (feet in the raw data, converted to m) and laser altimeter (m). Compared against the nominal drape altitude. |

Every column the aircraft delivers is described in
[docs/m02_correction_chain.md](../../docs/m02_correction_chain.md#columns-delivered-by-the-aircraft).

> **Note:** there is no pre-averaged magnetometer output from the aircraft. The sensor average is computed in step 6 of M2 processing (`average_sensors.py`).

### Steps 1–2 — GPS lag

Checks whether the magnetic readings and the GPS positions are out of sync (the magnetometer
reports each value slightly late, so anomalies end up shifted along the line). It measures the
shift on lines flown twice in opposite directions. If it is larger than the tolerance, the GPS
positions are shifted to correct it; otherwise the data is left unchanged.

```powershell
python -m src.m02_magnetics.run --steps 1,2
```

Everything is saved in `outputs/<campaign>/<run_name>/m02/step_01_02_lag/`:

| File | What it shows | Good sign |
|---|---|---|
| `lag_report.json` | `lag_median_s`: the measured lag. `lag_tolerable_s`: the limit above which it is corrected. `decision`: what was done | `decision` = `LAG_NEGLIGIBLE` |
| `lag_diagnosis_*.png` | The same line flown east and west, before and after aligning | The two curves nearly overlap |
| `lag_effect_map.png` | How much the data would change if the lag were applied (nT) | Mostly white |

**How to read the numbers.** The lag is the delay of the magnetometer. At the average speed
(38 m/s), 0.2 s means a position error of 7.6 m. It is only corrected if it exceeds
`lag_tolerable_s` (about 1.6 s, or 62 m: a quarter of the 250 m line spacing). Below that the
decision is `LAG_NEGLIGIBLE`: too small to matter, nothing is changed. With 0.2 s, the magnetic
value changes by less than 1 nT in 95 % of the points. `LAG_UNKNOWN` means there were no lines
flown in both directions to measure it.

The data continue to the next steps in `data/interim/<campaign>/<run_name>/m02/<date>/flight_XXXXX_m02.parquet`
(a copy of the M0 data plus `lag_applied`). Steps 3–8 run the same way: `--steps 3`, ...
How the lag is measured: [docs/m02_correction_chain.md](../../docs/m02_correction_chain.md).

---

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_X_line_Y.png` | 5-panel inspection figure per line |
| `outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_X_summary.png` | Summary grid (Panel 1 only) for a full flight |
| `outputs/<campaign>/<run_name>/m02/step_01_02_lag/` | `lag_report.json` (with the size of the effect in `effect_nT`), `lag_diagnosis_line<id>_line<id>.png`, `lag_effect_map.png` — see Steps 1–2 |
| `outputs/<campaign>/<run_name>/m02/step_<NN>_<name>/` | One GeoPackage and one map per later step |
| `outputs/<campaign>/<run_name>/m02/campaign_m02.gpkg`, `campaign_m02_map.png` | Consolidated GeoPackage and map of all selected lines, one layer per magnetic column. Only generated with step 8 |
| `data/interim/<campaign>/<run_name>/m02/<date>/flight_XXXXX_m02.parquet` | Per-flight data: copy of the M0 parquet plus `lag_applied`; GPS positions are shifted only if the decision is `LAG_SIGNIFICANT` |

---

## Reference

- Correction chain and the lag criterion explained: [docs/m02_correction_chain.md](../../docs/m02_correction_chain.md)
