# Correcciones magnéticas — Módulo 2

Este documento describe cada corrección de la cadena magnética: qué es, por qué existe,
cómo se detecta si es necesaria y cómo se aplica. Está orientado a cualquier campaña
futura, no solo Mongolia 2022.

---

## 0. Compensación en tiempo real (contexto — ya aplicada en los datos)

### Qué corrige

La interferencia magnética de la propia aeronave: motores, cableado, estructura metálica
y equipo electrónico generan un campo magnético superpuesto al campo geológico que se
quiere medir.

### Cómo se calculan los coeficientes

Se realiza un vuelo de calibración **cloverleaf** (trébol de cuatro hojas):
- El avión vuela en cuatro direcciones cardinales (N, E, S, O).
- En cada dirección ejecuta maniobras de cabeceo (pitch ±) y balanceo (roll ±).
- Esto genera 16 combinaciones de actitud que permiten resolver el sistema de
  ecuaciones de compensación (Tolles-Lawson), separando los tres tipos de
  interferencia: permanente (campo fijo de la aeronave), inducida (proporcional
  al campo externo) y eddy-current (proporcional a la variación temporal del campo).

Los coeficientes resultantes se cargan en el sistema de adquisición y se aplican
en tiempo real. El campo compensado se registra como `Mag1C` y `Mag2C`.

### Mongolia 2022

No se realizó vuelo cloverleaf. Se usaron coeficientes de calibración de una campaña
anterior. Consecuencia: existe un residuo heading-dependiente en Mag1C y Mag2C
(la compensación es imperfecta, especialmente en Mag2). Este residuo se trata en la
corrección de heading (Paso 5).

En los archivos MAG:
- `Mag1` / `Mag2` = campo total crudo (raw), sin compensar
- `Mag1C` / `Mag2C` = campo compensado en tiempo real con los coeficientes viejos

---

## 1. Corrección de lag GPS-magnetómetro

### Por qué existe

El magnetómetro de precesión de Larmor necesita completar un ciclo de precesión antes
de emitir cada valor. Este ciclo tarda ~0.3–0.5 s, lo que introduce una latencia física
que no puede eliminarse con el hardware: el magnetómetro no puede medir instantáneamente.

El GPS en cambio registra la posición prácticamente en tiempo real.

Resultado: cada valor magnético queda asociado a la posición GPS del **instante anterior**
a la medición real. A 200 km/h (≈ 55 m/s), 0.5 s de lag equivale a ~28 m de error
posicional.

### Efecto visible en los datos

La misma anomalía geológica aparece desplazada en **direcciones opuestas** al comparar
líneas voladas hacia el Este con líneas voladas hacia el Oeste:
- Líneas E: la anomalía aparece desplazada hacia el **oeste** (GPS registra posición anterior)
- Líneas O: la anomalía aparece desplazada hacia el **este**
- Diferencia total entre ambas = 2 × lag_m metros

### Cómo se estima desde los datos

Se comparan pares de líneas paralelas voladas en sentidos opuestos (ver `lag.py`):

1. Para cada par E/O, extraer el perfil Mag1C vs distancia acumulada.
2. Orientar ambos perfiles de Oeste a Este (invertir el de dirección O).
3. Restar la media de cada perfil (eliminar nivel DC).
4. Calcular la cross-correlación normalizada entre ambos perfiles.
5. El pico de la correlación en el offset k indica un desplazamiento total de
   2 × lag_m = k × paso_m metros.
6. lag_s = lag_m / velocidad_media = k × paso_m / (2 × v).
7. Repetir para todos los pares disponibles y reportar la mediana.

### Criterio de decisión automático

```
velocidad_media = mediana de velocidades GPS del conjunto de líneas (m/s)
lag_tolerable   = (espaciado_lineas_m / 4) / velocidad_media   [segundos]

|lag_mediano| < lag_tolerable  →  LAG_NEGLIGIBLE  (no corregir)
|lag_mediano| ≥ lag_tolerable  →  LAG_SIGNIFICANT (corregir)
```

El lag_tolerable es el máximo error de posición que puede pasar desapercibido dado
el espaciado entre líneas: un error de spacing/4 supera el umbral de medio-espaciado
entre puntos de grilla.

### Cómo se corrige

Se desplazan las columnas de posición GPS (`Xgps`, `Ygps`, `Zgps`) en el tiempo:
para cada instante t, se asigna la posición GPS registrada en t + lag_s, acercando
la posición al verdadero momento de la medición magnética.

### Mongolia 2022

Espaciado de líneas 250 m → lag_tolerable ≈ 1.1 s a 55 m/s.
El especialista no documentó corrección explícita, lo que sugiere que el lag fue
evaluado como negligible o que los coeficientes del sistema ya lo compensaban.

En Oasis Montaj: menú **Airborne QC → GPS Lag Correction**. Se puede estimar el lag
óptimo visualmente buscando el mínimo de corrugado en las intersecciones E/O.

---

## 2. Corrección diurna

### Qué corrige

La variación temporal del campo geomagnético causada por corrientes eléctricas en la
ionosfera (variación solar diurna) y perturbaciones magnetosféricas (tormentas
geomagnéticas). Esta variación es espacialmente suave y puede alcanzar 10–100 nT
en un día tranquilo, y hasta 1000 nT durante una tormenta.

### Fuente de datos

Estación de referencia en tierra (**Tagesgang**), muestreada a ~0.3 Hz. Registra el
campo total en nT durante todo el día de vuelo.

### Cómo se aplica

1. Interpolar el registro de la estación base al tiempo UTC de cada punto de vuelo
   (usar los timestamps sincronizados, no GPS).
2. Restar el valor interpolado de cada medición magnética.
3. Campo diurno corregido = Mag1C - Tagesgang_interpolado + valor_de_referencia.

El valor de referencia (campo base) es el nivel medio de la estación durante el vuelo,
o el valor IGRF en la posición de la estación.

### Mongolia 2022

Estación base operada durante todos los días de vuelo.
Campo de referencia regional: 59150 nT (IGRF en el centro del área).
Variaciones diurnas típicas de la región: ~20–50 nT/día en condiciones tranquilas.

En Oasis Montaj: menú **Mag Processing → Diurnal Correction**.

---

## 3. Remoción del IGRF

### Qué es el IGRF

El **International Geomagnetic Reference Field** (IGRF) es un modelo matemático del
campo geomagnético principal de la Tierra, generado por el núcleo externo líquido.
Varía suavemente en espacio (escala de miles de km) y en tiempo (variación secular,
~100 nT/año). La versión actual es IGRF-13.

### Por qué se resta

El objetivo del levantamiento es detectar anomalías magnéticas de origen geológico
(fallas, cuerpos intrusivos, mineralización). El campo total medido es la suma del
campo regional (IGRF, ~59150 nT en Mongolia) más la anomalía local (típicamente
< ±500 nT). Al restar el IGRF se obtiene la **Anomalía Magnética Residual (RMA)**,
que refleja exclusivamente las variaciones de susceptibilidad magnética de las rocas.

### Fórmula

```
RMA = Mag_diurnal_corrected - IGRF(lon, lat, alt_km, fecha_UTC)
```

### Implementación

Librería `ppigrf`. Entradas por punto:
- Longitud y latitud (grados decimales)
- Altitud en km sobre el elipsoide WGS84 (convertir Ralt de m a km + altura elipsoidal)
- Fecha UTC como `datetime.date`

### Mongolia 2022

Campo regional IGRF-13 en el área de estudio: ~59150 nT (valor de referencia en
`config/project.yaml`). La fecha de los vuelos cae en el período de validez de IGRF-13
(2020–2025), por lo que no se necesita interpolación entre generaciones del modelo.

En Oasis Montaj: menú **Mag Processing → IGRF**.

---

## 4. Corrección de heading

### Por qué existe incluso con compensación

Los coeficientes de compensación de tiempo real corrigen la interferencia teórica
calculada durante el vuelo cloverleaf. Si los coeficientes son imperfectos (o si
no hubo cloverleaf, como en Mongolia 2022), queda un residuo que varía
sistemáticamente con el heading del avión.

### Cuándo aplicar

Siempre medir; aplicar si el residuo supera ~1 nT.

### Cómo se mide

Se comparan los niveles medios de las líneas de producción voladas en sentidos opuestos
sobre el mismo terreno. La diferencia entre el nivel medio de las líneas E y el de las
líneas O para el mismo `line_id` es igual a 2 × heading_error.

### Implementación

Interpolación lineal sobre cuatro valores cardinales (N, E, S, O) en función del Yaw
de cada punto. Se construye una tabla de corrección (ΔMag vs Yaw) y se interpola
al heading de cada muestra.

### Mongolia 2022

Valores provistos por el especialista (Wackerle/Geointrepid):

| Sensor | N | E | S | O |
|--------|---|---|---|---|
| Mag1   | 0.0 nT | −0.5 nT | 0.0 nT | +0.5 nT |
| Mag2   | 0.0 nT | −1.7 nT | 0.0 nT | +1.7 nT |

Nota: no fue posible corregir las tie-lines (N-S) por datos insuficientes en esas
direcciones.

En Oasis Montaj: menú **Airborne QC → Heading Correction**.

---

## 5. Promedio de sensores magnéticos

### Cuándo promediar

Cuando ambos sensores (Mag1C y Mag2C) tienen ruido similar, el promedio reduce el
ruido por un factor √2, mejorando la resolución del levantamiento.

### Cuándo descartar uno

Si el ruido de un sensor es más del doble que el del otro, promediar lo empeora.
En ese caso se usa solo el sensor más limpio.

### Criterio de ruido

Desviación estándar del cuarto diferencial de la serie temporal (`mag_noise_nT`
calculado en M1). Un sensor con `mag_noise > 2 × mag_noise_del_otro` se descarta.

### Fórmula del promedio

```
Mag_avg = (Mag1C_corr + Mag2C_corr) / 2
```

Si se descarta uno: `Mag_avg = Mag1C_corr` (o Mag2C_corr según el caso).

---

## 6. Nivelación con líneas de amarre (tie-line levelling)

### Qué corrige

Diferencias de nivel (offsets de corriente continua) entre líneas de producción, causadas
por pequeñas derivas del sensor, errores residuales de compensación o variaciones
diurnas no capturadas. Se manifiestan como un corrugado de larga longitud de onda
paralelo a la dirección de vuelo.

### Cómo se aplica

1. Calcular el valor magnético en cada cruce entre líneas de producción y tie-lines.
2. Para cada cruce, la diferencia entre el valor de la línea de producción y el de
   la tie-line es el error de nivel local.
3. Ajuste por mínimos cuadrados sobre todos los cruces disponibles, distribuyendo
   el error entre producción y tie-lines de forma ponderada.
4. Aplicar la corrección resultante a cada línea.

### Requisito

Requiere que todas las líneas estén procesadas hasta el paso anterior (heading y promedio).

### Mongolia 2022

Líneas de producción E-W, tie-lines N-S cada 1500 m. La cantidad de intersecciones
disponibles depende de la cantidad de días/vuelos procesados. Con pocas tie-lines la
nivelación es menos robusta y puede quedar corrugado residual.

En Oasis Montaj: menú **Gridding → Tie-line Levelling**.

---

## 7. Micronivelación (decorrugación)

### Qué corrige

Corrugado de alta frecuencia espacial (longitud de onda del orden del espaciado entre
líneas) que persiste tras la nivelación con tie-lines. Suele tener amplitud < 1 nT y
se manifiesta en el grid como un patrón de rayas paralelas a las líneas de vuelo.

### Cómo se aplica

Filtro Butterworth direccional aplicado a cada perfil de línea:
1. Calcular la tendencia de larga longitud de onda de cada línea (filtro paso bajo).
2. La diferencia (residuo de alta frecuencia) se atenúa.
3. El corrugado corregido = señal original − fracción del residuo.

El corte de frecuencia y la fracción de atenuación son parámetros ajustables; valores
típicos: longitud de onda de corte ≈ 2–4 × espaciado entre líneas.

### Mongolia 2022

Espaciado 250 m → longitud de onda de corte ≈ 500–1000 m. La micronivelación se aplica
solo si el corrugado residual es visible en el grid previo.

En Oasis Montaj: menú **Gridding → Microlevelling**.
