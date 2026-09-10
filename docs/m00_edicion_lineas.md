# Edición de líneas — Módulo 0

Este documento explica los criterios que deciden si un punto pertenece a una línea de
vuelo y queda `line_valid = True`, por qué hay dos filtros separados (uno en M0, otro
en M1) y por qué no comparten el mismo umbral. Está motivado por un caso real: en el
vuelo `00427` del `22.04.2022`, algunos puntos de la línea `10010` quedaban cerca del
aeropuerto — antes de salir a volar la línea — con el `line_id` ya asignado.

---

## 1. Asignación de `line_id` (Wayp)

### Qué es

El campo `Wayp` del archivo MAG lo escribe el sistema de navegación de a bordo, en
tiempo real, durante el vuelo. Identifica qué línea está volando el avión en cada
instante; en blanco significa tránsito o viraje.

### Por qué puede fallar

El navegador puede "armar" la línea (`Wayp = 10010`) un poco antes de que el avión
llegue físicamente al corredor planeado, o dejarla armada un poco después de
terminarla. Los puntos tomados en ese margen heredan un `line_id` que no les
corresponde geométricamente — por ejemplo, puntos todavía sobre el aeropuerto.

### Editable

No. Viene grabado en el dato crudo (`read_mag.py`); no hay parámetro de software que
lo cambie.

---

## 2. Corte a lo largo del eje — `clip_to_line_extent` (along-track)

### Qué corrige

Puntos que quedan antes del inicio (A) o después del final (B) de la línea planeada,
medidos a lo largo del eje de vuelo.

### Cómo se aplica

Cada punto GPS se proyecta sobre el eje A→B de `TestSurveyNav.csv`:

    t = dot(P - A, unit(B - A))

Si `t < 0` (antes de A) o `t > longitud` (después de B), el punto se marca
`line_valid = False`. Es puramente geométrico — no tiene ningún umbral configurable,
depende solo de dónde están A y B en el plan de vuelo.

### Limitación

No detecta puntos que están **lateralmente** muy lejos del eje si su proyección igual
cae dentro de `[0, longitud]`. Eso es exactamente lo que pasa cuando el aeropuerto
está más o menos alineado con la dirección de la línea: el punto "parece" estar
dentro del rango a lo largo del eje, aunque en la práctica está a cientos de metros
o kilómetros del corredor real.

---

## 3. Corte lateral — `filter_by_cross_track` (`turn_filter_m`)

### Qué corrige

Puntos que están lejos **perpendicularmente** del eje planeado, sin importar si su
proyección a lo largo del eje cayó dentro de rango. Es el filtro que completa el
hueco que deja el paso 2.

### Caso real (motivador de este documento)

Vuelo `00427`, día `22.04.2022`, línea `10010`: puntos con `Wayp = 10010` ya armado
estando el avión todavía cerca del aeropuerto. Su distancia perpendicular al eje
A→B es grande, aunque la proyección a lo largo del eje cae dentro de `[0, longitud]`
— por eso el paso 2 solo no alcanza para sacarlos.

### Parámetro

`line_editing.turn_filter_m` en `config/project.yaml`. Es manual: no se lee de
`TestSurveyNav.csv`. Si se deja sin definir, este paso se saltea (no rompe nada).

---

## 4. Por qué NO se usa `CrossTrack` de `TestSurveyNav.csv` para este filtro

`CrossTrack` es el umbral de **calidad** del vuelo, usado en M1 (QC) para decidir si
una línea completa cumple la tolerancia planeada (`pass_cross_track`). Es a propósito
ajustado (del orden de 50 m).

Si se usara ese mismo número en M0 para decidir si un punto pertenece a la línea, se
descartarían puntos legítimos que se desviaron un poco más de lo ideal pero siguen
siendo parte real del vuelo — el dato se perdería antes de que M1 pudiera siquiera
evaluarlo, violando la regla del proyecto de que "los datos nunca se borran, solo se
marcan".

`turn_filter_m` es deliberadamente más laxo que `CrossTrack`: solo existe para
descartar outliers evidentes (aeropuerto, tránsito), no para hacer control de calidad
de línea. Esa es la razón por la que son dos números distintos, con dos orígenes
distintos (uno manual en `project.yaml`, el otro leído de `TestSurveyNav.csv`).

---

## Resumen

| Etapa | Qué decide | Umbral | De dónde sale | ¿Editable? |
|---|---|---|---|---|
| M0 — asignación `line_id` | Qué línea está volando | — | `Wayp` (dato crudo, MAG) | No |
| M0 — `clip_to_line_extent` | Antes/después de la línea (along-track) | — | Geometría A/B de `TestSurveyNav.csv` | No (fijo por el plan) |
| M0 — `filter_by_cross_track` | Outliers evidentes (cross-track) | `turn_filter_m` | `config/project.yaml` (manual) | Sí |
| M1 — `pass_cross_track` | Calidad de la línea completa (cross-track) | `CrossTrack` | `TestSurveyNav.csv` | No (regla del proyecto) |

Ver `src/m00_preparation/README.md` para cómo correr `prepare.py` y dónde se imprime
el valor de `turn_filter_m` usado en cada corrida.
