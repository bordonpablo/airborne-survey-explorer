# M2 — Magnetic correction chain

Each step removes one specific source of unwanted signal from the measured field.
The order is fixed: each correction assumes the previous one has already been applied.

---

## Columns produced at each step

| Step | Input | Output column | What is removed |
|------|-------|---------------|-----------------|
| 0 | Mag1_raw | **Mag1_C** | Aircraft magnetic interference (done in-flight by the compensation system) |
| 1–2 | Mag1_C | *(position corrected)* | GPS–magnetometer timing lag |
| 3 | Mag1_C | **Mag1_Diurnal** | Diurnal variation (ionospheric/magnetospheric noise, measured at base station) |
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
