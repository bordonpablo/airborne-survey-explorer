# M2 — Magnetic correction chain

Each step removes one specific source of unwanted signal from the measured field.
The order is fixed: each correction assumes the previous one has already been applied.

---

## Two sets of names

- **Aircraft names**: the columns of the MAG file, as they arrive in the M0 parquet
  (`Mag1C`, `MagL`, ...).
- **Specialist names**: the columns of the specialist's delivery
  (`data/reference/magnetics.ddf`: `Mag1_C`, `Mag_Grad`, ...). Every column the chain
  creates (`Mag1_Diurnal`, ..., `Mag_Final`) uses these names, so our results can be
  compared one-to-one with `data/reference/`.

Where a column exists in both, it is the same data (checked on flight 00456, 51,585
matched samples: median difference 0.000 nT, ratio 1.000).

| Aircraft (MAG file / M0 parquet) | Specialist (`magnetics.ddf`) | What it is |
|---|---|---|
| `Mag1`, `Mag2` | `Mag1_raw`, `Mag2_raw` | Raw total field of sensor 1 and 2 (nT) |
| `Mag1C`, `Mag2C` | `Mag1_C`, `Mag2_C` | Same field after the in-flight compensation (**C = compensated**) |
| `MagL` | `Mag_Grad` | Raw gradient between the two sensors (nT/m) |
| `MagLC` | `Mag_Grad_C` | Compensated gradient (nT/m) |
| `Mag1D`, `Mag2D` | — | 4th difference of `Mag1` / `Mag2` as recorded; noise of each sensor. Not in the specialist delivery |

Notes:

- `C` always means compensated. The lag correction does not touch any magnetic
  column: it shifts the GPS positions (see step 1–2).
- `MagL` is exactly `(Mag1 − Mag2) / 10.56` (checked on two flights); 10.56 is probably the
  separation between the sensors in metres (inference). `MagLC` has no such simple formula.
- `MagL`, `MagLC`, `Mag1D` and `Mag2D` are not used by any correction step.
  `average_sensors.py` computes its own 4th-difference noise.

### Where to see the aircraft's columns

| File | Which of these columns it has |
|---|---|
| Raw `MAG00xxx.txt` (in each day's folder under `data/raw/`) | All, as recorded |
| M0 parquet `data/interim/<campaign>/<run_name>/m00/<date>/flight_XXXXX_prepared.parquet` | All, one row per sample. **This is what M2 reads.** |
| M0 GeoPackage `outputs/.../m00/<date>/<date>.gpkg` (`export_qgis`) | Only `Mag1` and `Mag2` |
| M0 export `outputs/.../m00/selected_export/..._selected.{csv,xyz,gpkg}` (`export_selected`) | All |
| M2 `inspect_raw.py`: per-line PNG, `campaign_field_maps.png`, `campaign_raw.gpkg` | All |

Plotting them: [src/m02_magnetics/README.md](../src/m02_magnetics/README.md), Step 0.

---

## Columns produced at each step

Both sensors go through the chain in parallel (`Mag1_…` and `Mag2_…`) until step 6
combines them. The in-flight compensation already happened in the aircraft (`Mag1C` /
`Mag2C`); the chain starts from those. In code, the input of step 3 is read with the
aircraft names. Step numbers match the table in
[src/m02_magnetics/README.md](../src/m02_magnetics/README.md), where step 0 is only the visual inspection.

| Step | Input | Output column | What is removed |
|------|-------|---------------|-----------------|
| 1–2 | `Xgps`, `Ygps`, `Zgps` | same columns, shifted in time (+ `lag_applied`) | GPS–magnetometer timing lag. No magnetic column changes |
| 3 | `Mag1C`, `Mag2C` (specialist: `Mag1_C`, `Mag2_C`) | **Mag1_Diurnal**, **Mag2_Diurnal** | Diurnal variation (ionospheric/magnetospheric noise, measured at base station) |
| 4 | Mag1_Diurnal, Mag2_Diurnal | **Mag1_IGRF**, **Mag2_IGRF** | Earth's main field (IGRF-13 model). **First time the result is a small anomaly (~±tens of nT)** |
| 5 | Mag1_IGRF, Mag2_IGRF | **Mag1_IGRF_head**, **Mag2_IGRF_head** | Residual heading-dependent aircraft interference left by the in-flight compensation |
| 6 | Mag1_IGRF_head, Mag2_IGRF_head | **Mag_IGRF_head** (+ `sensor_used`) | — (plain average of both sensors; only the quieter one if the other is more than 2× noisier) |
| 7 | Mag_IGRF_head | **Mag_IGRF_head_level** | Line-to-line DC bias (levelling at tie-line crossover points) |
| 8 | Mag_IGRF_head_level | **Mag_Final** | High-frequency along-line corrugation (micro-levelling / decorrugation) |

---

## Why this order

- **Diurnal before IGRF**: the diurnal signal can be tens of nT — if not removed first, it biases the IGRF residual.
- **IGRF before heading**: the heading correction is fitted to the residual anomaly field; the main field (~59 000 nT) would completely dominate and hide the heading effect.
- **Average after heading**: both sensors must be corrected for heading independently before combining, because their heading responses can differ.
- **Levelling after everything else**: adjusts remaining DC offsets between lines; requires the signal to already be a clean anomaly.
- **Micro-levelling last**: a spatial filter — it can only work cleanly after levelling has removed the large line-to-line steps.

---

## What Mag_Final is

`Mag_Final` is the **Residual Magnetic Anomaly (RMA)**: the part of the measured field that remains after removing all known sources (aircraft, diurnal, Earth's main field, heading effect, and survey geometry artefacts). It represents only the geological signal.

It is **not** simply an average of the two magnetometers. The average happens at step 6 (`Mag_IGRF_head`); steps 7 and 8 are applied on top of that average.

---

## What is NOT mapped spatially

`BaseMag` and `Diurnal` are time series from a fixed ground station.
Plotting them on a map only reflects when the aircraft was over a given location,
not any spatial variation in the signal. They should be plotted as time series, not maps.

`IGRF` is spatially valid (it varies slowly with latitude and longitude) and is included in the maps.
