# M2 — Magnetic correction chain

Each step removes one specific source of unwanted signal from the measured field.
The order is fixed: each correction assumes the previous one has already been applied.

---

## Columns delivered by the aircraft

These come from the MAG file and keep the aircraft's own names. Everything the
chain adds later uses a different name (next section), so the two never mix.

| Column | What it is |
|---|---|
| `Mag1`, `Mag2` | Raw total field of magnetometer 1 and 2 (nT), before compensation. |
| `Mag1C`, `Mag2C` | The same field after the in-flight compensation system removed the aircraft's own magnetic interference (nT). **The chain starts from these.** |
| `MagL` | Raw gradient between the two sensors: exactly `(Mag1 − Mag2) / 10.56` (checked on two flights). Unit and meaning of 10.56 are not documented; probably nT per metre of sensor separation. Not used by any correction step. |
| `MagLC` | Compensated gradient. Close to `(Mag1C − Mag2C) / 12.9` but not exact. Not used by any correction step. |
| `Mag1D`, `Mag2D` | 4th difference of `Mag1` and `Mag2` as recorded by the system: a measure of each sensor's noise. Not used by any correction step; `average_sensors.py` computes its own 4th-difference noise. |

### Where to see these columns

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

The aircraft's in-flight compensation is **not** one of these steps: it is already
in `Mag1C` / `Mag2C`, which is where the chain starts. Every column below is created by M2.

| Step | Input | Output column | What is removed |
|------|-------|---------------|-----------------|
| 1–2 | `Mag1C` | *(position corrected)* | GPS–magnetometer timing lag |
| 3 | `Mag1C` | **Mag1_Diurnal** | Diurnal variation (ionospheric/magnetospheric noise, measured at base station) |
| 4 | Mag1_Diurnal | **Mag1_IGRF** | Earth's main field (IGRF-13 model). **First time the result is a small anomaly (~±tens of nT)** |
| 5 | Mag1_IGRF | **Mag1_IGRF_head** | Residual heading-dependent aircraft interference not removed in step 0 |
| 6 | Mag1_IGRF_head + Mag2_IGRF_head | **Mag_IGRF_head** | — (average of both sensors; quieter sensor gets more weight or the noisy one is discarded) |
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
