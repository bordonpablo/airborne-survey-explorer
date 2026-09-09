# Module 3 — Radiometric Processing

Processes gamma-ray spectrometry data (Medusa 4.3 L CsI) through three stages:
**A** (Python pre-processing) → **B** (GammAn FSA, manual) → **C** (Python post-processing, pending).

---

## Scripts — Stage A

| Script | Status | Role |
|--------|--------|-----|
| `inspect_spc.py` | ✅ | Visual QC of raw SPC — per-flight figures + campaign map |
| `read_spc.py` | ✅ | Reads and parses `SPC*.txt` files |
| `smooth_env.py` | ✅ | Smooths `Sralt`, `Sbaro`, `Stemp` (rolling median) |
| `export_gamman.py` | ✅ | Generates the two CSVs with decoded spectrum |
| `run_a.py` | ✅ | Stage A orchestrator |
| `run_c.py` | pending | Stage C orchestrator |

---

## Execution

```powershell
# QC inspection before processing
python -m src.m03_radiometry.inspect_spc 02.05.2022 00447

# Generate files for GammAn
python -m src.m03_radiometry.run_a 02.05.2022 00447

# Whole campaign
python -m src.m03_radiometry.run_a
```

---

## Stage A outputs

**Figures** → `outputs/<campaign>/<run_name>/m03/inspection/<date>/`

| File | What it shows |
|---------|-------------|
| `flight_XXXXX_spc.png` | Live time, gain, K/U/Th counts |
| `flight_XXXXX_smooth_qc.png` | Raw vs. smoothed Sralt/Sbaro/Stemp |
| `campaign_spc_map.png` | Total spatial count rate |

**CSVs for GammAn** → `data/interim/<campaign>/<run_name>/m03_gamman/input/<date>/flight_XXXXX/`

| File | Sralt/Sbaro/Stemp | Spectrum |
|---------|-------------------|---------|
| `SPC_decoded.csv` | original | ch000…ch255 uint16 LE |
| `SPC_gamman_ready.csv` | smoothed | ch000…ch255 uint16 LE |

---

## Stage B — GammAn (manual)

1. Import `SPC_gamman_ready.csv` into GammAn
2. Energy calibration + FSA + radon correction (**9-sample** window)
3. Export → `data/interim/<campaign>/<run_name>/m03_gamman/output/`

---

## Reference

- Specialist report: `data/reference/Readme_Especialista_02.txt`
- Output columns: `data/reference/Radiometrics.ddf`
