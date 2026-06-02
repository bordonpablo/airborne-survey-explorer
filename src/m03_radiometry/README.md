# Module 3 — Radiometric Processing

Processes gamma-ray spectrometry data (Medusa 4.3 L CsI) through three stages:
**A** (Python pre-processing) → **B** (GammAn FSA, manual) → **C** (Python post-processing, pending).

---

## Scripts — Etapa A

| Script | Status | Rol |
|--------|--------|-----|
| `inspect_spc.py` | ✅ | QC visual del SPC crudo — figuras por vuelo + mapa de campaña |
| `read_spc.py` | ✅ | Lee y parsea archivos `SPC*.txt` |
| `smooth_env.py` | ✅ | Suaviza `Sralt`, `Sbaro`, `Stemp` (rolling median) |
| `export_gamman.py` | ✅ | Genera los dos CSV con espectro decodificado |
| `run_a.py` | ✅ | Orquestador Etapa A |
| `run_c.py` | pendiente | Orquestador Etapa C |

---

## Ejecución

```powershell
# Inspección QC antes de procesar
python -m src.m03_radiometry.inspect_spc 02.05.2022 00447

# Generar archivos para GammAn
python -m src.m03_radiometry.run_a 02.05.2022 00447

# Toda la campaña
python -m src.m03_radiometry.run_a
```

---

## Salidas de Etapa A

**Figuras** → `outputs/<campaign>/<run_name>/m03/inspection/<date>/`

| Archivo | Qué muestra |
|---------|-------------|
| `flight_XXXXX_spc.png` | Live time, ganancia, cuentas K/U/Th |
| `flight_XXXXX_smooth_qc.png` | Sralt/Sbaro/Stemp crudos vs. suavizados |
| `campaign_spc_map.png` | Tasa de conteo total espacial |

**CSVs para GammAn** → `data/interim/<campaign>/<run_name>/m03_gamman/input/<date>/flight_XXXXX/`

| Archivo | Sralt/Sbaro/Stemp | Espectro |
|---------|-------------------|---------|
| `SPC_decoded.csv` | originales | ch000…ch255 uint16 LE |
| `SPC_gamman_ready.csv` | suavizados | ch000…ch255 uint16 LE |

---

## Etapa B — GammAn (manual)

1. Importar `SPC_gamman_ready.csv` en GammAn
2. Energy calibration + FSA + corrección de radón (ventana **9 muestras**)
3. Exportar → `data/interim/<campaign>/<run_name>/m03_gamman/output/`

---

## Referencia

- Reporte del especialista: `data/reference/Readme_Especialista_02.txt`
- Columnas del output: `data/reference/Radiometrics.ddf`
