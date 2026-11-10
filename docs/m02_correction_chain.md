# M2 — Magnetic correction chain

Each step removes one specific source of unwanted signal from the measured field.
The order is fixed: each correction assumes the previous one has already been applied.

---

## Columns delivered by the aircraft

These come from the MAG file and keep the aircraft's names; they arrive as they are in
the M0 parquet. Every column the chain creates later has its own name (next section).

| Column | What it is |
|---|---|
| `Mag1`, `Mag2` | Raw total field of sensor 1 and 2 (nT), before compensation |
| `Mag1C`, `Mag2C` | Same field after the in-flight compensation (**C = compensated**). **The chain starts from these** |
| `MagL` | Raw gradient between the two sensors (nT/m): exactly `(Mag1 − Mag2) / 10.56` (checked on two flights); 10.56 m is the separation between the two wingtip sensors |
| `MagLC` | Compensated gradient (nT/m) |
| `Mag1D`, `Mag2D` | 4th difference of `Mag1` / `Mag2` as recorded by the system: noise of each sensor |

Notes:

- `C` always means compensated. The lag correction does not touch any magnetic
  column: it shifts the GPS positions (see step 1–2).
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
`Mag2C`); the chain starts from those. Step numbers match the table in
[src/m02_magnetics/README.md](../src/m02_magnetics/README.md), where step 0 is only the visual inspection.

| Step | Input | Output column | What is removed |
|------|-------|---------------|-----------------|
| 1–2 | `Xgps`, `Ygps`, `Zgps` | same columns, shifted in time (+ `lag_applied`) | GPS–magnetometer timing lag. No magnetic column changes |
| 3 | `Mag1C`, `Mag2C` | **Mag1_Diurnal**, **Mag2_Diurnal** (+ `BaseMag`, `Diurnal`) | Diurnal variation (ionospheric/magnetospheric noise, measured at base station) |
| 4 | Mag1_Diurnal, Mag2_Diurnal | **Mag1_IGRF**, **Mag2_IGRF** | Earth's main field (IGRF-13 model). **First time the result is a small anomaly (~±tens of nT)** |
| 5 | Mag1_IGRF, Mag2_IGRF | **Mag1_IGRF_head**, **Mag2_IGRF_head** | Residual heading-dependent aircraft interference left by the in-flight compensation |
| 6 | Mag1_IGRF_head, Mag2_IGRF_head | **Mag_IGRF_head** (+ `sensor_used`) | — (plain average of both sensors; only the quieter one if the other is more than 2× noisier) |
| 7 | Mag_IGRF_head | **Mag_IGRF_head_level** | Line-to-line DC bias (levelling at tie-line crossover points) |
| 8 | Mag_IGRF_head_level | **Mag_Final** | High-frequency along-line corrugation (micro-levelling / decorrugation) |

---

## Steps 1–2: GPS–magnetometer lag

**What it is.** The magnetometer reports each value slightly late, so every reading is
assigned to a position a little ahead along the flight direction. The same anomaly then
appears shifted in opposite directions on lines flown in opposite directions.

**How it is measured.** Only a line flown twice in opposite directions (same track, east
and west) shows the effect without the geology getting in the way: neighbouring lines
(250 m apart) differ because of the geology, not because of the lag. For each such line,
the profile of both passes (mean of `Mag1C` and `Mag2C`) is put on the same easting grid
and cross-correlated:

    lag_s = k × step_m / (2 × v)

`k` is the shift in samples that best aligns the two passes (searched within ±2 s),
`step_m` the grid step (v × 0.1 s) and `v` the median ground speed (m/s). The two passes are
displaced 2 × lag × v from each other, hence the 2. The magnetometers sit on the wingtips,
10.56 m apart and on each side of the GPS: using the mean of the two cancels the lateral
offset. The lag of the campaign is the median over all such lines.

**Decision.** The tolerance is `(line_spacing_m / 4) / v`, with `line_spacing_m` from
`project.yaml` (250 m → 62.5 m of position error, 1.64 s at 38 m/s):

- `|lag| < tolerance` → `LAG_NEGLIGIBLE`: nothing is changed (`lag_applied = False`).
- `|lag| ≥ tolerance` → `LAG_SIGNIFICANT`: the GPS positions are shifted by
  `round(lag / 0.1 s)` samples; the last samples of each flight lose their position and are
  marked `line_valid = False`.
- No line flown in both directions → `LAG_UNKNOWN`: nothing is changed.

**Result for Mongolia 2022 (`test_001`).** 5 lines were flown in both directions (4 with
enough common track). Lags: +0.25, +0.20, +0.20 and 0.00 s; median 0.20 s, far below the
1.64 s tolerance → `LAG_NEGLIGIBLE`. If applied (0.2 s ≈ 7.6 m), the value at a point would
change by a median of 0.07 nT, below 0.9 nT in 95 % of the points, and 18 nT at most.

**Limits.** Only 4 pairs, with a resolution of 0.05 s. It assumes east–west lines. A fixed
offset between the sensors and the GPS along the flight direction cannot be told apart from
a timing lag.

---

## Step 3: Diurnal correction

**What it is.** External currents make the Earth's field vary during the day, by a few nT on a
quiet day. A base station fixed on the ground records that variation. For each airborne reading
the base value at the same instant is interpolated and its difference with the reference level is
subtracted:

    δ(t) = B_base(t) − B_ref        Mag1_Diurnal = Mag1C − δ(t)        Diurnal = −δ(t)

`B_ref` is `igrf_base_field_nT` in `project.yaml` (59150 nT). Only magnetic values change.

**How the base station is matched to the flights.** On **absolute UTC time** (date + time), never
on the time of day or on the name of the folder:

- Every `Tagesgang` file of every day folder is read. Each one crosses midnight UTC (the field
  campaign is in the local morning, UTC+8), so the file date comes from its header
  (`/ID ... file ...  21 IV 22`) and one day is added at each midnight crossed.
- Each flight has its date in the MAG `Date` column. The MAG `Time` is missing in about 13 % of the
  rows and has glitches (0.0, 0.1 s...) in a few: a time is only trusted if it keeps a constant
  difference with the `M3clk` clock, and the rest is interpolated along that clock.
- Base readings with quality flag below 94, zero values and spikes (more than 1 nT from the running
  median; normal scatter is about 0.25 nT) are discarded, about 1 % of the readings.
- A flight sample is only corrected if the base station has readings within 60 s around it. There
  is no extrapolation: the sample is left empty (NaN).

**What was found in this campaign (`test_001`).**

- 17 of the 18 flights are corrected. Variation between −10.3 and +8.6 nT; the correction added
  has a median of 3.2 nT, stays under 7.9 nT in 95 % of the points and reaches 10.3 nT at most.
- The file in the folder `24.04.2022` is a copy of the one in `22.04.2022`. The real recording of
  24 April (header `23 IV 22`) is stored in the folder `26.04.2022`. Matching by UTC time uses it
  correctly.
- Flight 00434 (26.04.2022, 04:50–06:05 UTC) has **no base station record**: the file in its folder is
  the recording of the night of 23–24 April. Its points are left empty from this step on.
- There is one base station (same site every day, 47.808° N, 107.574° E, readings every ~3 s).

**Limits.** The variation measured at one point is applied to the whole area, which is reasonable
for a survey of about 25 km. The correction is as good as the base station readings: it cannot
fix a flight without them.

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
