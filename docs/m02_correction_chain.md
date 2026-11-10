# M2 — Magnetic correction chain

Each step removes one specific source of unwanted signal from the measured field.
The order is fixed: each correction assumes the previous one has already been applied.

What was found in a particular campaign (numbers, problems, decisions) is not here:
see [findings_m02.md](findings_m02.md).

---

## Columns delivered by the aircraft

These come from the MAG file and keep the aircraft's names; they arrive as they are in
the M0 parquet. Every column the chain creates later has its own name (next section).

| Column | What it is |
|---|---|
| `Mag1`, `Mag2` | Raw total field of sensor 1 and 2 (nT), before compensation |
| `Mag1C`, `Mag2C` | Same field after the in-flight compensation (**C = compensated**). **The chain starts from these** |
| `MagL` | Raw gradient between the two sensors (nT/m): `(Mag1 − Mag2) / d`, with `d` the separation between the two wingtip sensors |
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
| 3 | `Mag1C`, `Mag2C` | **Mag1_Diurnal**, **Mag2_Diurnal** (+ `BaseMag`, `Diurnal`) | Diurnal variation (ionospheric/magnetospheric changes, measured at a base station) |
| 4 | Mag1_Diurnal, Mag2_Diurnal | **Mag1_IGRF**, **Mag2_IGRF** | Earth's main field (IGRF-13 model). **First time the result is a small anomaly around zero** |
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
differ because of the geology, not because of the lag. For each such line, the profile of
both passes (mean of `Mag1C` and `Mag2C`) is put on the same easting grid and
cross-correlated:

    lag_s = k × step_m / (2 × v)

`k` is the shift in samples that best aligns the two passes (searched within ±2 s),
`step_m` the grid step (`v` × sampling interval) and `v` the median ground speed (m/s). The
two passes are displaced 2 × lag × `v` from each other, hence the 2. The magnetometers sit on
the wingtips, on each side of the GPS: using the mean of the two cancels the lateral offset.
The lag reported is the median over all such lines.

**Decision.** The tolerance is `(line_spacing_m / 4) / v`: a quarter of the line spacing
(`line_spacing_m` in `project.yaml`) converted to seconds at the median ground speed.

- `|lag| < tolerance` → `LAG_NEGLIGIBLE`: nothing is changed (`lag_applied = False`).
- `|lag| ≥ tolerance` → `LAG_SIGNIFICANT`: the GPS positions are shifted by
  `round(lag / sampling interval)` samples; the last samples of each flight lose their position
  and are marked `line_valid = False`.
- No line flown in both directions → `LAG_UNKNOWN`: nothing is changed.

**Limits.** It needs lines flown twice in opposite directions; with few pairs the estimate is
coarse, and its resolution is limited by the sampling interval. It assumes east–west lines (it
works on the easting). A fixed offset between the sensors and the GPS along the flight
direction cannot be told apart from a timing lag.

---

## Step 3: Diurnal correction

**What it is.** External currents make the Earth's field vary during the day. A base station
fixed on the ground records that variation. For each airborne reading, the base value at the
same instant is interpolated, compared with a fixed reference level, and the difference is
removed from the airborne value.

**What each name means** (all in nT):

| Name | What it is |
|---|---|
| `BaseMag(t)` | The field measured by the ground base station at time `t`, interpolated to the time of each airborne sample. Column `BaseMag` |
| `B_ref` | A fixed reference level (`diurnal_reference_nT` in `project.yaml`). It is a chosen constant, not computed from the IGRF. Only how far the base station is from it matters |
| `δ(t) = BaseMag(t) − B_ref` | The **diurnal variation**: how far above (+) or below (−) the reference the field is at that instant |
| `Diurnal` (column) | The **correction to add**: `Diurnal = −δ(t) = B_ref − BaseMag(t)` |
| `Mag1_Diurnal` (column) | The data after the correction: `Mag1C + Diurnal = Mag1C − δ(t)` |

"Diurnal" is used in three ways: the phenomenon (the variation `δ`), the column `Diurnal`
(the correction, which has the **opposite sign** of `δ`, the Geosoft/Oasis convention) and the
suffix of `Mag1_Diurnal` (data already corrected).

**Example** (illustrative numbers). With `B_ref = 59 000`: if at some instant the base reads
59 004, then `δ = +4` (the field is 4 nT above the reference), `Diurnal = −4`, and an airborne
reading of 59 120 at that instant becomes `59 120 − 4 = 59 116`. If the base had read 58 997,
`δ = −3`, `Diurnal = +3` and the same reading would become 59 123.

The value of `B_ref` does not change the shape of any anomaly: a different `B_ref` shifts all
the data by the same constant. What matters is that it is the same for the whole survey, so no
level difference appears between days. Only magnetic values change.

**Raw and filtered base station.** The base station curve has two versions: *raw* (bad
readings and spikes removed) and *filtered* (moving average of `base_filter_window_s` seconds,
to keep the noise of the base station out of the airborne data). `base_station_use` (`raw` or
`filtered`) chooses which one is subtracted; the plot shows both.

**How the base station is matched to the flights.** On **absolute UTC time** (date + time), never
on the time of day or on the name of the folder:

- Every `Tagesgang` file of every day folder is read. A file can cross midnight UTC, so its date
  comes from its header and one day is added at each midnight crossed.
- Each flight has its date in the MAG `Date` column. The MAG `Time` can be missing or have
  glitches (0.0, 0.1 s...): a time is only trusted if it keeps a constant difference with the
  `M3clk` clock, and the rest is interpolated along that clock.
- Base readings with a low quality flag, zero values and spikes (far from the running median)
  are discarded.
- A flight sample is only corrected if the base station has readings within 60 s around it. There
  is no extrapolation: the sample is left empty (NaN).
- Periods without a recording can be filled from a supplementary table
  (`base_station_supplement`, built by `base_supplement.py`). It is used only where the
  campaign's own base station has no reading, and its readings are marked in the plot.

**Limits.** The variation measured at one point is applied to the whole area, which is reasonable
when the survey is small compared with the distance over which the external field varies. The
correction is as good as the base station readings: it cannot fix a flight without them.

---

## Why this order

- **Diurnal before IGRF**: the diurnal signal can be tens of nT — if not removed first, it biases the IGRF residual.
- **IGRF before heading**: the heading correction is fitted to the residual anomaly field; the main field (tens of thousands of nT) would completely dominate and hide the heading effect.
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
