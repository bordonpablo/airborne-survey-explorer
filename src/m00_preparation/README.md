# Módulo 0 — Data Preparation

Lee los archivos crudos de cada vuelo (MAG, GGA, SPC), sincroniza los sensores
por timestamp y guarda el resultado como Parquet listo para M01.

## Scripts

| Script | Rol |
|---|---|
| `prepare.py` | **Punto de entrada principal.** Procesa uno o todos los vuelos. |
| `export_qgis.py` | **Verificación visual.** Genera un GeoPackage para QGIS. |
| `read_mag.py` | Función interna — parsea archivos MAG (~10 Hz, magnetómetro + actitud) |
| `read_gga.py` | Función interna — parsea archivos GGA (~10 Hz, GPS diferencial) |
| `read_spc.py` | Función interna — parsea archivos SPC (~1 Hz, espectrómetro) |
| `read_tagesgang.py` | Función interna — parsea archivos de estación base magnética |
| `read_survey_nav.py` | Función interna — lee `TestSurveyNav.csv` (líneas planificadas) |
| `sync_sensors.py` | Función interna — sincroniza sensores con `merge_asof`, recorta transitorios |

## Selección de campaña

La campaña activa se define en `config/project.yaml`:

```yaml
campaign:
  name: "Mongolia_2022"
  raw_data_path: "data/raw/Mongolia_2022/Daten_Nisleg_2022"
```

Para procesar otra campaña, se edita ese archivo. No es necesario pasar
ningún argumento al script.

## Flujo de ejecución

### Paso 1 — Preparar los vuelos

Procesar toda la campaña activa (todos los días y todos los vuelos):

```bash
python -m src.m00_preparation.prepare
```

Procesar solo un día:

```bash
python -m src.m00_preparation.prepare 22.04.2022
```

Procesar un único vuelo de un día concreto:

```bash
python -m src.m00_preparation.prepare 22.04.2022 00427
```

El argumento de fecha debe coincidir exactamente con el nombre de la carpeta
en el directorio de datos crudos (formato `DD.MM.YYYY`).
El ID de vuelo es el número de 5 dígitos del archivo MAG correspondiente
(p. ej. `MAG00427.txt` → `00427`).

Por cada vuelo procesado el script:
1. Lee MAG, GGA y SPC
2. Sincroniza los tres sensores sobre el eje temporal de GGA (`merge_asof`)
3. Recorta los primeros y últimos 5 s de cada línea de vuelo (transitorios)
4. Guarda en `data/interim/<campaña>/<fecha>/flight_XXXXX_prepared.parquet`

### Paso 2 — Verificar en QGIS (opcional)

```bash
python -m src.m00_preparation.export_qgis
```

Genera `outputs/<campaña>/verification_YYYYMMDD_HHMMSS.gpkg` con tres capas:

- `survey_plan` — líneas planificadas (UTM 48N)
- `flight_tracks` — trazas GPS reales punto a punto
- `flight_lines` — cada segmento `(flight_id, line_id)` como LineString

Cada ejecución produce un archivo nuevo con timestamp para poder comparar
distintas corridas sobre el mismo set de datos.

## Salidas

| Ruta | Contenido |
|---|---|
| `data/interim/<campaña>/<fecha>/flight_XXXXX_prepared.parquet` | DataFrame sincronizado, input para M01 |
| `outputs/<campaña>/verification_YYYYMMDD_HHMMSS.gpkg` | GeoPackage para verificación en QGIS |
