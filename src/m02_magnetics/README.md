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
| `run.py` | **Main entry point.** Reads `line_selection.csv` and runs steps 1–2 (lag correction). |
| `inspect_raw.py` | **Raw inspection.** Four-panel PNG per line before any correction. |
| `lag.py` | **GPS lag estimation and correction.** Cross-correlation of opposite-direction pairs. |
| `validate.py` | **Specialist comparison.** Reads Geosoft .dat/.ddf files and compares columns. |
| `validate.py` — see also `data/reference/` | Reads Geosoft .dat/.ddf and compares specialist columns against ours. |
| `diurnal.py` | Diurnal correction (base station subtraction). [pendiente] |
| `igrf.py` | **IGRF-13 removal.** Computes and subtracts IGRF total field at each sample point using ppigrf. |
| `heading.py` | **Heading correction.** Empirical DC offset per heading direction (E/W). No calibration flight required. |
| `average_sensors.py` | **Sensor average.** Combines Mag1 and Mag2 using fourth-difference noise criterion. |
| `levelling.py` | **Tie-line levelling.** Crossover-based DC offset per production line. See docstring for eastern-edge limitation. |
| `microlevelling.py` | **Micro-levelling.** Along-line minus across-line moving average — removes residual corrugation, produces `Mag_Final`. |

---

## Correction order

| Step | Script | Description |
|---|---|---|
| 0 | `inspect_raw.py` | Visual inspection of raw vs compensated signal before any correction |
| 1 | `lag.py` | Estimate GPS–magnetometer lag by cross-correlation of E/W line pairs |
| 2 | `lag.py` | Apply lag correction (only if decision = LAG_SIGNIFICANT) |
| 3 | `diurnal.py` | Subtract base-station diurnal variation interpolated to flight time |
| 4 | `igrf.py` | ✅ Remove IGRF-13 reference field (ppigrf, input: lon, lat, alt km, UTC date) |
| 5 | `heading.py` | ✅ Empirical heading correction — DC offset estimated from mean difference between E and W lines |
| 6 | `average_sensors.py` | ✅ Combine Mag1 and Mag2 — fourth-difference noise test; discard if one sensor > 2× noisier |
| 7 | `levelling.py` | ✅ Crossover DC offset per production line (tie lines as reference). Eastern edge limited by 5 missing ties — see specialist report. |
| 8 | `microlevelling.py` | ✅ Along-line minus across-line smooth — corrugation removed, produces `Mag_Final` |

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
```

Produces the following outputs (all under `outputs/<campaign>/<run_name>/m02/inspection/`):

| File | Scope | Contents |
|---|---|---|
| `<date>/flight_X_line_Y.png` | per line | 4-panel profile (total field, gradient, attitude, altimetry) |
| `<date>/flight_X_summary.png` | per flight | Panel 1 thumbnails for all lines |
| `campaign_field_maps.png` | **whole campaign** | Scatter maps in lon/lat — one subplot per column (Mag1, Mag1C, Mag2, Mag2C, MagL, MagLC) |
| `campaign_raw.gpkg` | **whole campaign** | GeoPackage (EPSG:4326) — one layer per column, all selected lines |

The consolidated map and GeoPackage are only generated when running without arguments (whole-campaign mode). At M2 stage, line selection is already decided — the consolidated view is what matters.

**Panels and columns shown:**

| Panel | Columns | Description |
|---|---|---|
| 1 — Total field | `Mag1`, `Mag1C`, `Mag2`, `Mag2C` | Raw vs compensated for each sensor. `Mag1C`/`Mag2C` = aircraft interference removed by the onboard compensation system during flight. |
| 2 — Vertical gradient | `MagL`, `MagLC` | `MagL` = Mag1 − Mag2 (raw difference between the two sensors). `MagLC` = compensated gradient. Sensitive to shallow sources. |
| 3 — Attitude | `Roll`, `Pitch`, `Yaw` | Aircraft orientation. Used to diagnose heading-dependent noise. |
| 4 — Altimetry | `Ralt`, `Lalt` | Radar and laser altimeter (height above ground). Compared against the nominal drape altitude. |

> **Note:** there is no pre-averaged magnetometer output from the aircraft. The sensor average is computed in step 6 of M2 processing (`average_sensors.py`).

### Step 1 — Estimate GPS lag

The lag function requires a concatenated DataFrame with all selected lines.
Call it from a script or the Python REPL:

```python
import pandas as pd
import yaml
from pathlib import Path
from src.m02_magnetics.lag import estimate_lag

PROJECT_ROOT = Path('.')
with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
    config = yaml.safe_load(f)

campaign = config['campaign']['name']
run_name = config['campaign']['run_name']
interim  = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name

# Load all selected parquets (adapt to your selection)
frames = []
for pq in interim.rglob('flight_*_prepared.parquet'):
    frames.append(pd.read_parquet(pq))
df = pd.concat(frames, ignore_index=True)
df = df[df['line_valid'] & df['line_id'].notna()]

resultado = estimate_lag(df, config)
print(resultado)
```

Terminal output example:
```
[M2 LAG] Velocidad media     : 55.3 m/s
[M2 LAG] Paso espacial       : 5.5 m
[M2 LAG] Pares E/O encontrados: 12
[M2 LAG] ──────────────────────────────────────────────────
[M2 LAG] Lag mediano   : +0.41 s
[M2 LAG] Lag std       : 0.08 s
[M2 LAG] Lag tolerable : 1.13 s  (= spacing/4 / v)
[M2 LAG] Pares usados  : 12
[M2 LAG] Decisión      : LAG_NEGLIGIBLE
```

### Step 2 — Apply lag (only if LAG_SIGNIFICANT)

```python
from src.m02_magnetics.lag import apply_lag

df_corregido = apply_lag(df_vuelo, lag_s=resultado['lag_median_s'])
```

### Validate against specialist data

```python
from src.m02_magnetics.validate import read_specialist_data, compare_columns

df_ref = read_specialist_data(
    'data/reference/Mongolia_2022.dat',
    'data/reference/Mongolia_2022.ddf',
)
stats = compare_columns(df_ours, 'Mag1C', df_ref, 'MAG1COMP', label='Mag1C compensado')
```

---

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_X_line_Y.png` | 4-panel inspection figure per line |
| `outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_X_summary.png` | Summary grid (Panel 1 only) for a full flight |
| `outputs/<campaign>/<run_name>/m02/lag_report.json` | Lag estimation result (median, std, decision) |
| `outputs/<campaign>/<run_name>/m02/campaign_m02.gpkg` | Consolidated GeoPackage — all selected lines after lag correction, one layer per magnetic column |
| `data/interim/<campaign>/<run_name>/<date>/flight_XXXXX_m02.parquet` | Per-flight parquet with lag correction applied |
| `outputs/<campaign>/<run_name>/reference/` | Specialist reference maps and GeoPackage — see `data/reference/README.md` |

---

## Reference

- Specialist processing report and reference data: `data/reference/`
- Correction chain explained: [docs/m02_correction_chain.md](../../docs/m02_correction_chain.md)
