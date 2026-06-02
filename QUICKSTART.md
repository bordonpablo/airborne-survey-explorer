# Quick start — run a full campaign from scratch

## 0. Setup (once per machine)

```powershell
python -m venv airborne-env
airborne-env\Scripts\Activate.ps1
pip install -r requirements.txt
```

Edit `config/project.yaml`: set `campaign.name`, `run_name`, `raw_data_path`.

---

## 1. M0 — Prepare flights

```powershell
python -m src.m00_preparation.prepare            # all flights
```

Check result in QGIS:

```powershell
python -m src.m00_preparation.export_qgis        # produces .gpkg per day
```

Build the line selection table:

```powershell
python -m src.m00_preparation.build_line_selection
```

Open `data/interim/<campaign>/<run_name>/line_selection.csv` and set
`selected = False` for any bad segments.

---

## 2. M1 — Quality control

```powershell
python -m src.m01_qc.run                         # compute metrics for all selected lines
python -m src.m01_qc.viewer                      # interactive viewer (click lines on map)
```

After reviewing, update `selected` in `line_selection.csv` if needed.

Output: `outputs/<campaign>/<run_name>/m01/`

---

## 3. Reference data (once, before M2)

```powershell
python data/reference/plot_reference.py          # maps + GeoPackage of specialist data
python data/reference/plot_corrections_impact.py # how large was each correction?
```

Output: `outputs/<campaign>/<run_name>/reference/`

---

## 4. M2 — Magnetic corrections

```powershell
# Inspect raw signal before any correction
python -m src.m02_magnetics.inspect_raw

# Run full correction chain (steps 1–8)
python -m src.m02_magnetics.run

# Run specific steps only
python -m src.m02_magnetics.run --steps 1,2      # lag only
python -m src.m02_magnetics.run --steps 3        # diurnal only
python -m src.m02_magnetics.run --steps 4        # IGRF only
python -m src.m02_magnetics.run --steps 5        # heading only
python -m src.m02_magnetics.run --steps 6        # sensor average only
python -m src.m02_magnetics.run --steps 7        # levelling only
python -m src.m02_magnetics.run --steps 8        # micro-levelling only
```

Output: `outputs/<campaign>/<run_name>/m02/`
Per-step GeoPackages + maps: `step_02_lag.gpkg`, `step_03_diurnal.gpkg`, etc.
Final column: `Mag_Final` in each `_m02.parquet`.

---

## 5. M3 — Radiometry (Etapa A — pre-GammAn)

### Inspección QC del espectrómetro

```powershell
python -m src.m03_radiometry.inspect_spc              # toda la campaña
python -m src.m03_radiometry.inspect_spc 02.05.2022   # un día
```

Genera dos figuras por vuelo en `outputs/<campaign>/<run_name>/m03/inspection/<date>/`:

| Figura | Qué muestra |
|--------|-------------|
| `flight_XXXXX_spc.png` | Live time, estabilidad de ganancia, cuentas brutas K/U/Th |
| `flight_XXXXX_smooth_qc.png` | Sralt/Sbaro/Stemp crudos vs. suavizados — verificar que el filtro es correcto |

### Preparar archivos para GammAn

```powershell
python -m src.m03_radiometry.run_a 02.05.2022 00447   # un vuelo
python -m src.m03_radiometry.run_a                    # toda la campaña
```

Genera por vuelo en `data/interim/<campaign>/<run_name>/m03_gamman/input/<date>/flight_XXXXX/`:

| Archivo | Qué es |
|---------|--------|
| `SPC_gamman_ready.csv` | Columnas SPC + espectro decodificado (ch000…ch255) con Sralt/Sbaro/Stemp **suavizados**. Importar en GammAn. |
| `SPC_decoded.csv` | Igual pero con valores **originales** de Sralt/Sbaro/Stemp. Referencia. |

### Etapa B — GammAn (manual)

1. Importar `SPC_gamman_ready.csv` en GammAn
2. Ejecutar energy calibration + FSA + corrección de radón (ventana 9 muestras)
3. Exportar resultado en `data/interim/<campaign>/<run_name>/m03_gamman/output/`

### Etapa C — post-GammAn (pendiente)

Ver `src/m03_radiometry/README.md` para el estado de implementación.

---

## 6. M4 — Gridding

```powershell
python -m src.m04_gridding.run
```

Output: `outputs/<campaign>/<run_name>/m04/`

| File | Contents |
|---|---|
| `Mag_Final.tif` | Residual Magnetic Anomaly — 60 m grid, EPSG:32648 |
| `rtp.tif` | Reduction to Pole |
| `analytic_signal.tif` | Analytic signal amplitude |
| `horizontal_gradient.tif` | Horizontal gradient magnitude |
| `vertical_derivative.tif` | First vertical derivative |
| `tilt_derivative.tif` | Tilt derivative (°) |
| `Mag_products_map.png` | Six-panel quick-look |

---

## Output folder structure

```
outputs/<campaign>/<run_name>/
├── m00/        QGIS GeoPackages and inspection plots (M0)
├── m01/        QC reports and detail plots (M1)
├── m02/        Inspection PNGs, per-step GeoPackages and maps (M2)
├── m04/        GeoTIFF grids and derivative products (M4)
└── reference/  Specialist ground-truth maps and GeoPackage
```

```
data/interim/<campaign>/<run_name>/
├── m00/<date>/flight_XXXXX_prepared.parquet        ← output of M0
├── m02/<date>/flight_XXXXX_m02.parquet             ← output of M2 (Mag_Final inside)
├── m03_gamman/input/<date>/flight_XXXXX/
│   ├── SPC_gamman_ready.csv                        ← M3 Etapa A input for GammAn
│   └── SPC_decoded.csv                             ← M3 Etapa A reference
├── m03_gamman/output/                              ← GammAn output (placed manually)
├── line_selection.csv                              ← bridge M0→M1→M2 (edit manually)
└── config.yaml                                     ← config snapshot
```

---

## Key files

| File | Purpose |
|---|---|
| `config/project.yaml` | All campaign parameters — edit before running anything |
| `data/interim/<campaign>/<run_name>/line_selection.csv` | Which segments enter M2 — the only file you edit manually |
| `docs/m02_correction_chain.md` | What each M2 correction does and in what order |
| `src/m04_gridding/README.md` | Gridding method, parameters, outputs |
| `NOTES.md` | Detailed workflow notes and decisions |
