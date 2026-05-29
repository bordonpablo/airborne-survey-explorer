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
| `data/reference/plot_reference.py` | **Reference maps.** One map + one GeoPackage layer per intermediate column. Run once. |
| `data/reference/plot_corrections_impact.py` | **Correction impact.** Bar chart of magnitudes, spatial difference maps, and profile along one line. |
| `diurnal.py` | Diurnal correction (base station subtraction). [pendiente] |
| `igrf.py` | IGRF-13 removal (ppigrf). [pendiente] |
| `heading.py` | Heading correction (residual aircraft interference). [pendiente] |
| `average_sensors.py` | Average Mag1C and Mag2C (or select the quieter one). [pendiente] |
| `levelling.py` | Tie-line levelling (least-squares at crossover points). [pendiente] |
| `microlevelling.py` | Microlevelling / decorrugation (directional Butterworth filter). [pendiente] |

---

## Correction order

| Step | Script | Description |
|---|---|---|
| 0 | `inspect_raw.py` | Visual inspection of raw vs compensated signal before any correction |
| 1 | `lag.py` | Estimate GPS–magnetometer lag by cross-correlation of E/W line pairs |
| 2 | `lag.py` | Apply lag correction (only if decision = LAG_SIGNIFICANT) |
| 3 | `diurnal.py` | Subtract base-station diurnal variation interpolated to flight time |
| 4 | `igrf.py` | Remove IGRF-13 reference field (ppigrf, input: lon, lat, alt km, UTC date) |
| 5 | `heading.py` | Correct residual heading-dependent error (coeff. from specialist) |
| 6 | `average_sensors.py` | Combine Mag1C and Mag2C; discard if one sensor noise > 2× the other |
| 7 | `levelling.py` | Least-squares level adjustment at traverse/tie crossover points |
| 8 | `microlevelling.py` | Attenuate high-frequency corrugation remaining after levelling |

---

## Execution

### Step 0 — Inspect raw signal

```powershell
# All lines of a flight
python -m src.m02_magnetics.inspect_raw 22.04.2022 00447

# One specific line
python -m src.m02_magnetics.inspect_raw 22.04.2022 00447 1001
```

Produces one PNG per line (4 panels) and a summary PNG with all lines on a grid:

```
outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_00447_line_1001.png
outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_00447_summary.png
```

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

### Reference data — specialist outputs

Run once before starting implementation. Generates ground-truth maps and a
GeoPackage to compare against at each correction step.

```powershell
# Maps + GeoPackage of all intermediate columns
python data/reference/plot_reference.py

# Correction impact: magnitude chart, difference maps, profile along one line
python data/reference/plot_corrections_impact.py
```

Output folder: `outputs/<campaign>/<run_name>/reference/`

---

## Outputs

| Path | Contents |
|---|---|
| `outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_X_line_Y.png` | 4-panel inspection figure per line |
| `outputs/<campaign>/<run_name>/m02/inspection/<date>/flight_X_summary.png` | Summary grid (Panel 1 only) for a full flight |
| `outputs/<campaign>/<run_name>/m02/lag/lag_diagnosis_lineA_lineB.png` | Cross-correlation diagnostic for one E/W pair |
| `outputs/<campaign>/<run_name>/reference/ref_<col>.png` | One map per specialist column |
| `outputs/<campaign>/<run_name>/reference/ref_summary_*.png` | Summary panels per group (mag1, mag2, finals) |
| `outputs/<campaign>/<run_name>/reference/specialist_magnetics.gpkg` | GeoPackage — one layer per column |
| `outputs/<campaign>/<run_name>/reference/impact_magnitudes.png` | Bar chart of correction magnitudes (nT) |
| `outputs/<campaign>/<run_name>/reference/impact_diff_maps.png` | Spatial maps of step-by-step differences |
| `outputs/<campaign>/<run_name>/reference/impact_profile.png` | Field evolution along one survey line |

---

## Reference

- Specialist processing report and reference data: `data/reference/`
- Correction chain explained: [docs/m02_correction_chain.md](../../docs/m02_correction_chain.md)
