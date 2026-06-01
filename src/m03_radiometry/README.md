# Module 3 — Radiometric Processing

Processes gamma-ray spectrometry data from the Medusa 4.3 L CsI detector
to produce corrected ground concentrations of Potassium (% K), Uranium (eppm U)
and Thorium (eppm Th), plus Air Absorbed Dose Rate (nGy/h).

The processing chain is split into **three separate stages** because the core
spectral deconvolution (Full Spectral Analysis, FSA) is performed by the external
software **GammAn** (Medusa Radiometrics) and cannot be replicated in Python.

---

## Architecture

```
[Etapa A — Python]              [Etapa B — GammAn, manual]       [Etapa C — Python]
                                                                  
  Raw SPC files                   GammAn input files               GammAn output
  per flight (1 Hz)               (smoothed SPC)                   ASCII files
        │                                │                               │
   read_spc.py                  Energy calibration               read_gamman.py
   smooth_env.py                Spectral stabilisation           sync_nav.py
   export_gamman.py             FSA deconvolution                despike.py  (U only)
        │                       Radon correction (9 samples)     levelling.py
        ▼                       Height / HSTP correction         microlevelling.py
  m03_gamman/input/             Export ASCII                     dose_rate.py
                                        │                               │
                                        ▼                               ▼
                                m03_gamman/output/           m03/ parquets finales
```

---

## Scripts

| Script | Stage | Status | Rol |
|--------|-------|--------|-----|
| `inspect_spc.py` | A | ✅ | QC visual del SPC crudo — 5 paneles por vuelo + mapa de campaña |
| `read_spc.py` | A | ✅ | Lee y parsea archivos `SPC*.txt` crudos |
| `smooth_env.py` | A | ✅ | Suaviza `Sralt`, `Sbaro`, `Stemp` antes de GammAn |
| `run_a.py` | A | pendiente | Orquestador Etapa A — lee SPCs, suaviza, exporta para GammAn |
| `export_gamman.py` | A | pendiente | Exporta el SPC suavizado en formato ASCII para GammAn |
| `run_c.py` | C | pendiente | Orquestador Etapa C — desde GammAn output hasta parquets finales |
| `read_gamman.py` | C | pendiente | Parsea el output ASCII de GammAn |
| `sync_nav.py` | C | pendiente | Merge por `M2clk` con parquets de M0 para añadir coords GPS y `line_id` |
| `despike.py` | C | pendiente | Filtro adaptativo no-lineal (sólo Uranio, per especialista) |
| `dose_rate.py` | C | pendiente | Calcula `Tot_nGyph` a partir de K/U/Th concentraciones |
| `levelling.py` | C | pendiente | Tie-line levelling independiente por canal |
| `microlevelling.py` | C | pendiente | Micro-levelling por canal |

---

## Cadena de procesamiento completa

| Paso | Stage | Script | Descripción | Estado |
|------|-------|--------|-------------|--------|
| A.1 | A | `read_spc.py` | Lee los archivos SPC crudos y parsea todas las columnas | ✅ |
| A.2 | A | `smooth_env.py` | Suaviza `Sralt`, `Sbaro`, `Stemp` con ventana configurable | ✅ |
| A.3 | A | `export_gamman.py` | Exporta un archivo ASCII por vuelo para importar en GammAn | ✅ |
| — | B | GammAn | Estabilización espectral + FSA + corrección de radón + altura | externo |
| C.1 | C | `read_gamman.py` | Lee el output de GammAn → `Pot_corr`, `Ura_corr`, `Tho_corr`, etc. | pendiente |
| C.2 | C | `sync_nav.py` | `merge_asof` por `M2clk` con M0 → coords, `line_id`, `line_valid` | pendiente |
| C.3 | C | `despike.py` | Filtro adaptativo sobre `Ura_corr` → `Ura_corr_clean`; K y Th pasan sin cambio | pendiente |
| C.4 | C | `levelling.py` | Crossover-based levelling por canal: K, U, Th, Tot\_cps independientes | pendiente |
| C.5 | C | `dose_rate.py` | `Tot_nGyph_level` desde K/U/Th levellados | pendiente |
| C.6 | C | `microlevelling.py` | Micro-levelling independiente por canal | pendiente |
| C.7 | C | `dose_rate.py` | `Tot_nGyph_final` desde K/U/Th finales | pendiente |

---

## Columnas del archivo SPC crudo

El prefijo **`S`** identifica al espectrómetro (sensor M2 en el DAS). Cada fila es
una muestra a ~1 Hz.

### Tiempo y posición

| Columna | Unidad | Descripción |
|---------|--------|-------------|
| `M2clk` | ms | Reloj del sistema desde el arranque del DAS — eje de sincronización compartido con MAG (M1clk) y GGA (M3clk) |
| `Sxgps`, `Sygps` | ° | Longitud y latitud GPS del espectrómetro |
| `Szgps` | m | Altitud GPS sobre el nivel del mar |
| `Swayp` | — | Nombre de la línea de vuelo asignado por el sistema de navegación; en blanco durante transits y virajes |

### Altímetro

| Columna | Unidad | Descripción |
|---------|--------|-------------|
| `Sralt` | m | **Altímetro de radar** — distancia al terreno directamente debajo del avión. No es altitud sobre el mar (eso es `Szgps`). Es la variable más importante para la corrección de altura en radiometría. Se suaviza antes de GammAn. |

Valor esperado en vuelo normal: 80–120 m (drape nominal 100 m). Valores
persistentemente > 120 m indican que la corrección de altura del FSA será menos
confiable. Valores = 0 o constantes indican falla del sensor.

### Sensores ambientales — voltaje crudo vs. valor calibrado

El sistema registra dos versiones de cada variable ambiental. Siempre se usan
los valores calibrados.

| Voltaje crudo | Valor calibrado | Unidad | Qué mide |
|---------------|-----------------|--------|----------|
| `BaroV` | `Sbaro` | mBar | Presión barométrica. GammAn la usa para la corrección HSTP (normalización a condiciones estándar). Disminuye durante el ascenso. |
| `TempV` | `Stemp` | °C | Temperatura del aire. Afecta la densidad del aire y por tanto la corrección de altura. Cambia lentamente con la altitud y la hora del día. |
| `HumdV` | `Shumd` | % | Humedad relativa. Influencia menor en el procesamiento; se entrega como referencia. |

Ambas versiones se suavizan antes de GammAn (`Sbaro_smooth`, `Stemp_smooth`).
El ruido de alta frecuencia en estos canales migra directamente a las
concentraciones finales de K/U/Th.

### Tiempo de adquisición del detector

| Columna | Unidad | Descripción |
|---------|--------|-------------|
| `Sreal` | s | **Real time** — duración total de la muestra, típicamente exactamente 1.000 s |
| `Slive` | s | **Live time** — tiempo durante el cual el detector estuvo disponible para registrar pulsos. Siempre ≤ `Sreal`. |

La diferencia `Sreal − Slive` es el **dead time**: instantes en que el detector
estaba ocupado procesando un evento anterior y no podía registrar uno nuevo.

`livetime_frac = Slive / Sreal` debería ser > 0.99 en condiciones normales.
Si cae por debajo de 0.99 significa que el detector perdió pulsos — las
concentraciones resultantes estarán **subestimadas** en esas zonas porque
GammAn no puede recuperar los pulsos perdidos.

### Tasa de conteo total y cuentas por ventana IAEA

| Columna | Unidad | Descripción |
|---------|--------|-------------|
| `Srate` | cps | **Total count rate** — todos los fotones detectados por segundo, de cualquier energía. Indicador general de actividad del detector y de la concentración de radioelementos debajo del avión. |
| `Sk` | cps | Cuentas en la ventana de energía del **K-40** (~1.46 MeV) — proxy crudo de potasio. |
| `Su` | cps | Cuentas en la ventana del **Bi-214** (~1.76 MeV) — proxy crudo de **uranio**. El Bi-214 es producto de desintegración del U-238 en la serie del radio. |
| `Sth` | cps | Cuentas en la ventana del **Tl-208** (~2.61 MeV) — proxy crudo de **torio**. El Tl-208 es producto de desintegración del Th-232. |

**Importante**: `Sk`, `Su`, `Sth` son el método de ventana IAEA clásico —
sencillo, ruidoso, sin corrección de altura ni radón. No son concentraciones
FSA. Sirven para QC visual (el detector registró señal, hay variabilidad
geológica) pero **no se usan en el procesamiento final**.

### Estabilización espectral — Sa0, Sa1, Sa2

El cristal CsI cambia ligeramente de ganancia con la temperatura y las
variaciones de alta tensión. Sin corrección, los picos del espectro se corren
de canal y el sistema confundiría energías. La estabilización espectral aplica
una corrección polinómica en tiempo real para mantener los picos centrados:

```
canal_corregido = Sa0 + Sa1 · canal + Sa2 · canal²
```

| Columna | Descripción |
|---------|-------------|
| `Sa0` | Offset del polinomio (término independiente) |
| `Sa1` | Ganancia lineal |
| `Sa2` | Corrección cuadrática — muy pequeña (~−0.0005), típicamente constante |

Valores constantes a lo largo del vuelo indican detector estable. Una deriva
sostenida en `Sa0` o `Sa1` indica inestabilidad de ganancia del cristal
(típicamente por cambios térmicos); GammAn deberá compensarla durante la
re-estabilización post-proceso.

### Espectro crudo — Sbin

| Columna | Descripción |
|---------|-------------|
| `Sbin` | Los 512 canales del espectro gamma completo, codificados en hexadecimal. Cada canal cuenta los fotones detectados en ese rango de energía. Es la materia prima que GammAn deconvoluciona con FSA para producir K, U y Th. Se pasa a GammAn sin modificar. |

---

## Etapa A — Preparación de SPCs para GammAn

### Qué hace

GammAn necesita las mediciones ambientales del avión — altímetro de radar, presión
barométrica, temperatura — sin ruido de alta frecuencia para aplicar correctamente
las correcciones de altura y HSTP durante el FSA. El ruido en esos canales migra
directamente a las concentraciones finales.

La única preparación requerida antes de GammAn es suavizar esas tres columnas.
Todo lo demás en el SPC debe llegar a GammAn sin modificar.

### Formato del archivo SPC crudo

Los archivos `SPC*.txt` tienen una fila por segundo (~1 Hz). Columnas principales:

| Columna | Descripción |
|---------|-------------|
| `M2clk` | Timestamp en ms desde el arranque del sistema DAS — eje de sincronización con MAG y GGA |
| `Swayp` | Waypoint / Line ID (en blanco fuera de líneas de producción) |
| `Sxgps`, `Sygps`, `Szgps` | Posición GPS del espectrómetro |
| `Sralt` | Altímetro de radar — **a suavizar** |
| `Sbaro`, `Stemp`, `Shumd` | Presión, temperatura, humedad — **Sbaro y Stemp a suavizar** |
| `Sreal`, `Slive` | Tiempo real y live time de adquisición |
| `Srate` | Tasa de conteo total (cps) |
| `Sk`, `Su`, `Sth` | Cuentas por ventana IAEA en tiempo real — **no son concentraciones FSA** |
| `Sa0`, `Sa1`, `Sa2` | Parámetros de estabilización espectral |
| `Sbin` | Espectro crudo de 512 canales en codificación hex — **no tocar** |

### Reglas críticas

**Incluir el vuelo entero.** GammAn realiza la estabilización espectral (energy
calibration) usando todas las muestras del vuelo para construir la función de
transferencia del detector. Filtrar solo a filas de líneas de producción degrada
la calibración. El campo `Swayp` puede estar en blanco fuera de líneas — esas
filas deben incluirse igualmente.

**No modificar `Sbin`.** Es el espectro crudo que FSA deconvoluciona contra la
función de respuesta del detector Medusa. Cualquier modificación corrompe la
calibración espectral.

**`Sk`, `Su`, `Sth` son solo referencia de QC.** Son cuentas obtenidas por un
método de ventana IAEA simple aplicado en tiempo real. No se usan en el pipeline
de FSA y no deben confundirse con `Pot_corr`/`Ura_corr`/`Tho_corr`.

**Un archivo de salida por vuelo.** GammAn procesa un vuelo a la vez. Días con
múltiples vuelos (por ejemplo, 28.04.2022 tiene SPC00437, SPC00438, SPC00439,
SPC00440) producen cuatro archivos separados.

**Ventana de suavizado** configurable en `project.yaml` bajo `radiometry.smooth_window_sralt`
y `radiometry.smooth_window_env`. El especialista usó un filtro corto; 5 muestras
(= 5 s a 1 Hz) es el punto de partida.

### Inspección QC — antes de suavizar y exportar

```powershell
# Todos los vuelos de la campaña
python -m src.m03_radiometry.inspect_spc

# Un día específico
python -m src.m03_radiometry.inspect_spc 02.05.2022

# Un vuelo específico
python -m src.m03_radiometry.inspect_spc 02.05.2022 00447
```

Genera una figura de 5 paneles por vuelo (ver descripción de paneles más abajo)
y un mapa de campaña si se ejecuta sin argumentos.

### Preparación para GammAn (pendiente: run_a.py)

```powershell
# Todos los vuelos de la campaña
python -m src.m03_radiometry.run_a

# Un día específico
python -m src.m03_radiometry.run_a 02.05.2022

# Un vuelo específico
python -m src.m03_radiometry.run_a 02.05.2022 00447
```

### Salidas de Etapa A

| Ruta | Contenido |
|------|-----------|
| `data/interim/<campaign>/<run_name>/m03_gamman/input/flight_XXXXX_spc.txt` | SPC suavizado, listo para GammAn |
| `outputs/<campaign>/<run_name>/m03/etapa_a/<date>/flight_XXXXX_smooth.png` | Perfil de Sralt/Sbaro/Stemp antes y después del suavizado |
| `outputs/<campaign>/<run_name>/m03/etapa_a_report.csv` | Resumen: filas por vuelo, rangos de columnas ambientales |

---

## Etapa B — GammAn (manual, software externo)

GammAn es software propietario de Medusa Radiometrics. Los siguientes pasos se
ejecutan manualmente por el operador.

1. Abrir GammAn
2. Importar el archivo desde `m03_gamman/input/flight_XXXXX_spc.txt`
3. Ejecutar **energy calibration** (estabilización espectral) usando la calibración
   del detector Medusa 4.3 L CsI de la campaña
4. Ejecutar **FSA deconvolution** — produce concentraciones corregidas por
   background, altura y HSTP
5. Corrección de **Radón** — ventana de integración: **9 muestras** (confirmado
   en el reporte del especialista para Mongolia 2022)
6. Exportar como ASCII en `data/interim/<campaign>/<run_name>/m03_gamman/output/flight_XXXXX_gamman.txt`

El archivo exportado debe contener al menos:
`Pot_raw`, `Pot_corr`, `Ura_raw`, `Ura_corr`, `Tho_raw`, `Tho_corr`,
`Tot_raw`, `Tot_corr`, `Radon`, `Cosmics`, `LifeTime`.
Opcionalmente también `SpecEC` y `SpecNASVD` (los espectros procesados).

> **Nota sobre NASVD**: el especialista calcula los espectros NASVD (Noise Adjusted
> Single Value Decomposition, 7 componentes principales por vuelo) pero **no los usa
> en el procesamiento**. Se entregan como referencia para reprocesamiento futuro.
> No forman parte del pipeline de concentraciones.

---

## Etapa C — Post-GammAn (pendiente)

### C.1 — Leer output de GammAn (`read_gamman.py`)

Parsea el archivo ASCII exportado por GammAn. El formato exacto (separador,
nombres de columnas) depende de la versión de GammAn. La función devuelve un
DataFrame indexado por `M2clk` — el timestamp de sincronización compartido con
GGA y MAG en todo el pipeline.

### C.2 — Sincronización con navegación GPS (`sync_nav.py`)

El output de GammAn contiene datos espectrales y el timestamp interno del DAS
(`M2clk`), pero **no tiene coordenadas GPS**. Este paso hace `merge_asof()` sobre
`M2clk` contra el parquet de M0, igual que en la sincronización de sensores de M0.
Después del merge, cada fila tiene `East`, `North`, `Lon`, `Lat`, `GPS_Alt`,
`line_id`, `line_valid` y `flight_id` de la navegación preparada.

### C.3 — Filtro de spikes (`despike.py`)

El especialista confirmó que **sólo el Uranio** presenta spikes espurios en este
dataset. K y Th pasan sin filtro (`_clean = _corr`).

El filtro es un **filtro adaptativo no-lineal**: dentro de una ventana deslizante,
una muestra se marca como spike si se desvía de la mediana local más de N sigma
de la dispersión local. Las muestras marcadas se reemplazan por la mediana local.
Ventana y umbral configurables en `project.yaml`.

### C.4 — Tie-line levelling (`levelling.py`)

Corrección de offset DC basada en crossovers entre líneas de producción y tie
lines. K, U, Th y Tot\_cps se levellan **de forma independiente** — los offsets
no se comparten entre canales.

**Limitación borde este**: 5 tie lines faltan en el borde este del área de vuelo
(condiciones climáticas adversas). El especialista resolvió esto generando **tie
lines artificiales**: micro-levellar la grilla en primera pasada, resamplear a lo
largo de las posiciones de tie planificadas, y usar esos valores muestreados como
datos de tie. Este procedimiento se evaluará en una etapa separada.

### C.5 y C.7 — Dose Rate (`dose_rate.py`)

El Dose Rate se calcula **dos veces**: una desde las concentraciones levelladas
(`Tot_nGyph_level`) y otra desde las concentraciones finales microlevelladas
(`Tot_nGyph_final`). La fórmula IAEA es:

```
Tot_nGyph = k_K · K + k_U · eU + k_Th · eTh
```

Coeficientes IAEA (configurables en `project.yaml`):

| Coeficiente | Valor | Unidad |
|-------------|-------|--------|
| k_K | 1.505 | nGy/h por % K |
| k_U | 0.653 | nGy/h por eppm U |
| k_Th | 0.287 | nGy/h por eppm Th |

### C.6 — Micro-levelling (`microlevelling.py`)

Elimina la corrugación residual línea a línea usando la diferencia entre el suavizado
a lo largo de la línea y el suavizado transversal a las líneas (mismo algoritmo
que M2). Se aplica de forma independiente a cada canal.

---

## Columnas del DataFrame final

| Columna | Unidad | Origen |
|---------|--------|--------|
| `line_id`, `flight_id`, `line_valid` | — | M0 (vía sync\_nav) |
| `East`, `North` | m (UTM-48N) | M0 |
| `Lon`, `Lat`, `GPS_Alt` | DD.dd / m | M0 |
| `Rad_Alt` | m | GammAn (Sralt suavizado) |
| `Humidity`, `Pressure`, `Temperature` | % / mBar / °C | GammAn (suavizado) |
| `LifeTime` | s | GammAn |
| `Pot_raw`, `Ura_raw`, `Tho_raw`, `Tot_raw` | cps | GammAn — ventanas IAEA sobre SpecEC |
| `Pot_corr`, `Ura_corr`, `Tho_corr`, `Tot_corr` | % K / eppm U / eppm Th / cps | GammAn — FSA |
| `Pot_corr_clean`, `Ura_corr_clean`, `Tho_corr_clean` | ídem | `despike.py` |
| `Pot_level`, `Ura_level`, `Tho_level`, `Tot_cps_level` | ídem | `levelling.py` |
| `Tot_nGyph_level` | nGy/h | `dose_rate.py` (desde \_level) |
| `Pot_final`, `Ura_final`, `Tho_final`, `Tot_cps_final` | ídem | `microlevelling.py` |
| `Tot_nGyph_final` | nGy/h | `dose_rate.py` (desde \_final) |
| `Radon`, `Cosmics` | — / cps | GammAn |

---

## Parámetros en `project.yaml`

```yaml
radiometry:
  gamman_input_path: "data/interim/<campaign>/<run_name>/m03_gamman/input"
  gamman_output_path: "data/interim/<campaign>/<run_name>/m03_gamman/output"
  smooth_window_sralt: 5       # muestras (= 5 s a 1 Hz)
  smooth_window_env: 5         # muestras para Sbaro y Stemp
  despike_window: 7            # muestras para el filtro adaptativo
  despike_threshold_sigma: 3.0
  max_usable_altitude_m: 120.0  # umbral para inspección visual (Sralt)
  dose_rate_k_coeff: 1.505      # nGy/h por % K  (IAEA)
  dose_rate_u_coeff: 0.653      # nGy/h por eppm U
  dose_rate_th_coeff: 0.287     # nGy/h por eppm Th
```

---

## Salidas finales del módulo

| Ruta | Contenido |
|------|-----------|
| `data/interim/<campaign>/<run_name>/m03_gamman/input/flight_XXXXX_spc.txt` | SPC suavizado para GammAn (Etapa A) |
| `data/interim/<campaign>/<run_name>/m03_gamman/output/flight_XXXXX_gamman.txt` | Output de GammAn (colocado manualmente, Etapa B) |
| `data/interim/<campaign>/<run_name>/m03/<date>/flight_XXXXX_m03.parquet` | Parquet radiométrico final por vuelo (Etapa C) |
| `outputs/<campaign>/<run_name>/m03/campaign_m03.gpkg` | GeoPackage consolidado, una capa por columna final |
| `outputs/<campaign>/<run_name>/m03/campaign_m03_map.png` | Mapa K, U, Th, Dose Rate lado a lado |

---

## Referencia

- Reporte de procesamiento del especialista: `data/reference/Readme_Especialista_02.txt`
- Formato y nombres de columnas de referencia: `data/reference/Radiometrics.ddf`
- Datos procesados de referencia: `data/reference/Radiometrics_example.dat`
