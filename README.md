# LANOT_ceniza

Sistema de detección de ceniza volcánica del Popocatépetl utilizando datos del ABI de los satélites GOES-East (GOES-16 hasta abril de 2025, GOES-19 desde entonces).

## Descripción

Este proyecto procesa datos de nivel 2 (L2) del instrumento ABI (Advanced Baseline Imager) de GOES-East para detectar y analizar ceniza volcánica emitida por el volcán Popocatépetl. 

El sistema utiliza múltiples canales infrarrojos y productos derivados para:
- Calcular diferencias de temperatura de brillo (BTD - Brightness Temperature Difference)
- Determinar el ángulo cenital solar (SZA) usando geometría esférica y efemérides precisas
- Analizar la fase de las nubes (Phase) para distinguir entre ceniza y otros tipos de nubes
- Generar productos de detección de ceniza volcánica

### Productos ABI utilizados

- **ACTP**: Cloud Top Phase (Fase de la cima de nube)
- **C04**: Canal 4 (1.38 μm) - Cirrus
- **C07**: Canal 7 (3.9 μm) - Infrarrojo de onda corta
- **C11**: Canal 11 (8.4 μm) - Infrarrojo de onda larga
- **C13**: Canal 13 (10.3 μm) - Infrarrojo limpio
- **C14**: Canal 14 (11.2 μm) - Infrarrojo de onda larga
- **C15**: Canal 15 (12.3 μm) - Infrarrojo sucio

**Nota:** Las coordenadas geográficas (latitud/longitud) se calculan automáticamente a partir de la proyección GOES, eliminando la necesidad del producto NAV.

## Instalación

### Requisitos previos

- Python 3.10 o superior
- pip (gestor de paquetes de Python)

### Configuración del ambiente

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/asierra/LANOT_ceniza.git
   cd LANOT_ceniza
   ```

2. **Crear un ambiente virtual:**
   ```bash
   python3 -m venv .venv
   ```

3. **Activar el ambiente virtual:**
   
   En Linux/Mac:
   ```bash
   source .venv/bin/activate
   ```
   
   En Windows:
   ```bash
   .venv\Scripts\activate
   ```

4. **Instalar el paquete:**
   ```bash
   pip install .
   ```

   > Para desarrollo (los cambios al código se reflejan sin reinstalar):
   > ```bash
   > pip install -e .
   > ```

### Dependencias principales

- **xarray**: Lectura y manipulación de datos NetCDF multidimensionales
- **netcdf4**: Backend para lectura de archivos NetCDF
- **rioxarray**: Extensión de xarray para operaciones geoespaciales y reproyección
- **numpy**: Operaciones numéricas y manejo de arrays
- **scipy**: Filtros y operaciones de procesamiento de imágenes (ndimage)
- **skyfield**: Cálculos astronómicos precisos (posición del Sol, efemérides JPL)
- **pyproj**: Transformaciones de sistemas de coordenadas y proyecciones (GOES ↔ lat/lon)
- **affine**: Geotransformaciones afines para georreferenciación
- **python-dateutil**: Parsing de fechas en formato ISO 8601
- **rasterio**: Escritura del GeoTIFF con tabla de colores
- **matplotlib** (opcional): solo para `lanot-compare-ash`; se instala con `pip install '.[comparacion]'`

Las imágenes PNG con mapa base ya no las genera este paquete: se hacen con [LANOT_tools](https://github.com/asierra/LANOT_tools) a partir del GeoTIFF (ver [la refactorización de mayo de 2026](doc/2026-05-01_refactorizacion.md)).

Para correr las pruebas: `pip install -e '.[pruebas]'` y `pytest`.

## Uso

### Detección de Ceniza (`lanot-detect-ash`)

### Ejecución básica

Procesar el instante más reciente automáticamente:

```bash
lanot-detect-ash
```

Procesar un instante específico:

```bash
lanot-detect-ash --path /data/ceniza/l2 --date-tree --instant 20191001731
```

Especificar archivo o directorio de salida:

```bash
# Nombre de archivo específico
lanot-detect-ash --instant 20191001731 --output resultado_ceniza.tif

# Directorio (genera nombre automático: ceniza_20191001731.tif)
lanot-detect-ash --instant 20191001731 --output /data/resultados/

# Con reproyección, el sufijo _geo se agrega automáticamente
lanot-detect-ash --instant 20191001731 --clip popocatepetlgeo --output /data/resultados/
# Genera: /data/resultados/ceniza_20191001731_geo.tif
```

### Parámetros de línea de comandos

- `--path` / `-p`: Ruta al directorio que contiene los archivos NetCDF L2 (por defecto: `/data/ceniza/l2`)
- `--date-tree`: Busca los archivos en `--path/AAAA/MM/DD` según el instante
- `--instant` / `-m`: Instante a procesar: `YYYYjjjHHMM` (día juliano) o `YYYYMMDDHHMM`; también un rango del mismo día, `YYYYjjjHHMM-HHMM` o `YYYYMMDDHHMM-HHMM`. Si no se especifica, se calcula el más reciente
- `--output`: Ruta de salida para el GeoTIFF. Puede ser:
  - **Un archivo**: `resultado.tif` - Guarda con ese nombre
  - **Un directorio**: `/data/salida/` - Genera automáticamente `ceniza_[instante].tif` (o con sufijo `_geo` si se reproyecta)
  - **Por defecto**: `./ceniza_[instante].tif`
- `--clip`: Región para recortar el resultado. Opciones disponibles:
  - `centromex`: Centro de México (proyección GOES nativa)
  - `centromexgeo`: Centro de México (reproyectado a lat/lon EPSG:4326)
  - `popocatepetl`: Región del Popocatépetl (proyección GOES nativa)
  - `popocatepetlgeo`: Región del Popocatépetl (reproyectado a lat/lon EPSG:4326)
  - `ashpaper`, `ashpapergeo`: Región del artículo (la que usa la operación en tahan)
- `--dry-run`: Solo revisa qué instantes tienen todos los archivos
- `--sin-qml`: No escribe el estilo de QGIS junto al GeoTIFF
- `--verbose` / `-v`: Mensajes detallados

### Ejemplos de uso

**Procesamiento completo sin recorte:**
```bash
lanot-detect-ash --path /data/ceniza/2019/spring --instant 20190871402
```

**Recorte a región específica (proyección GOES):**
```bash
lanot-detect-ash --instant 20190871402 --clip centromex
lanot-detect-ash --instant 20190871402 --clip popocatepetl
```

**Recorte con reproyección a coordenadas geográficas:**
```bash
lanot-detect-ash --instant 20190871402 --clip centromexgeo
lanot-detect-ash --instant 20190871402 --clip popocatepetlgeo --output /data/salida/
```

**Un rango de instantes en un directorio:**
```bash
lanot-detect-ash --instant 201903010800-1430 --path /data/ceniza/l2 --date-tree --output /data/procesados/
# Genera: ceniza_20190600802.tif, ceniza_20190600807.tif, ...
```

### Regiones de recorte predefinidas

- **centromex**: [-107.23, 22.72, -93.84, 14.94] (lon_min, lat_max, lon_max, lat_min)
- **popocatepetl**: [-100.26, 20.58, -96.85, 18.29]
- **ashpaper**: [-102.418, 22.474, -96.294, 17.547]

El recorte se realiza **antes** de procesar los datos, mejorando significativamente el rendimiento y reduciendo el uso de memoria.

### Rendimiento

El cálculo más costoso, la desviación estándar local del kernel 5×5, usa filtros uniformes sobre x, x² y el conteo de valores válidos, sin procesos en paralelo (desde octubre de 2026; antes usaba `generic_filter` repartido entre todos los núcleos).

- **Dominio completo CONUS** (1500×2500 píxeles): unos segundos por escena, casi todo lectura de archivos.
- **Recortes regionales**: los datos se recortan antes de leerse, así que el tiempo baja con el tamaño de la región.

### Salida

GeoTIFF de una banda (uint8) con tabla de colores, en la proyección geoestacionaria del satélite (o EPSG:4326 si se reproyecta), y junto a él un estilo de QGIS con el mismo nombre (`ceniza_X.qml`). Valores:

| valor | significado | color |
|---|---|---|
| 0 | sin ceniza | transparente (con el `.qml`) |
| 1 | ceniza confirmada (CA) | rojo |
| 2 | probabilidad alta (HAP) | naranja |
| 3 | probabilidad baja (LAP) | amarillo |
| 4, 5 | reservados (los usaban versiones anteriores; ver `ash.cpt`) | — |
| 255 | sin datos (NoData) | transparente |

La paleta de un TIFF no guarda transparencia, así que sin el `.qml` QGIS dibuja el 0 en negro. QGIS carga el `.qml` solo si está junto al GeoTIFF con el mismo nombre; si no, se puede cargar a mano el `ceniza.qml` del repositorio (Propiedades → Simbología → Estilo → Cargar estilo). `--sin-qml` evita escribirlo. Entre mayo y octubre de 2026 el 0 se guardaba como 255.

El archivo incluye georreferenciación completa y puede ser visualizado en cualquier software GIS (QGIS, ArcGIS, etc.).

**Nombres de archivo con sufijo `_geo`:**

Cuando se usa reproyección a coordenadas geográficas (opciones que terminan en "geo"), los archivos de salida incluyen automáticamente el sufijo `_geo`:

```bash
# Sin reproyección
lanot-detect-ash --instant 20191001731
# Genera: ceniza_20191001731.tif

# Con reproyección
lanot-detect-ash --instant 20191001731 --clip popocatepetlgeo
# Genera: ceniza_20191001731_geo.tif
```

### Comparación de resultados (`lanot-compare-ash`)

Requiere matplotlib (`pip install '.[comparacion]'`). Permite comparar visualmente dos archivos GeoTIFF de clasificación (p. ej., resultado de TeraScan vs. el de este paquete) y genera una imagen PNG con matrices de confusión y estadísticas.

#### Ejecución básica

```bash
lanot-compare-ash referencia.tif resultado.tif
```

#### Parámetros

- `ref`: Archivo GeoTIFF de referencia (ej. salida TeraScan).
- `test`: Archivo GeoTIFF a evaluar.
- `--output` / `-o`: Nombre del PNG de salida (por defecto: `comp_<nombre_test>.png`).

#### Ejemplo

```bash
lanot-compare-ash ceniza_20190871402_terascan.tif ceniza_20190871402.tif \
  --output comparacion.png
```

## Estructura del proyecto

```
LANOT_ceniza/
├── detect_ash.py       # Detección de ceniza (lanot-detect-ash)
├── compare_ash.py      # Comparación con resultados de referencia (lanot-compare-ash)
├── pyproject.toml      # Configuración del paquete instalable
├── ceniza.qml          # Estilo de QGIS para los GeoTIFF (lo escribe también junto a cada salida)
├── ash.cpt             # Paleta de colores histórica (incluye las clases 4 y 5, ya no usadas)
├── tests/              # Pruebas (pytest) y recortes de datos reales para la regresión
├── herramientas/       # Comparación entre versiones y generación de datos de prueba
├── operacion/          # Cadena de baja latencia en tahan (ver operacion/README.md)
├── doc/                # Planes y decisiones del proyecto, con fecha
└── LICENSE
```

## Metodología

### Algoritmo de detección de ceniza volcánica

El algoritmo implementa un método multi-espectral de detección basado en diferencias de temperatura de brillo (BTD) y características de fase de nube, adaptado a las condiciones de iluminación solar:

#### 1. Cálculo del ángulo cenital solar (SZA)

Para cada píxel de la imagen se calcula el SZA usando un método optimizado:

1. Obtiene la posición del Sol (RA/Dec) usando efemérides precisas de JPL (DE421)
2. Calcula el tiempo sideral de Greenwich (GST) 
3. Determina el ángulo horario local (LHA) para cada punto: `LHA = GST + Longitud - RA`
4. Aplica geometría esférica: `cos(SZA) = sin(lat) × sin(dec) + cos(lat) × cos(dec) × cos(LHA)`

Este enfoque es más eficiente que la vectorización directa con Skyfield para arrays grandes.

#### 2. Diferencias de temperatura de brillo (BTD)

Se calculan tres diferencias espectrales clave:

- **delta1** = C13 - C15 (BTD 10.3-12.3 μm) - Indicador principal de ceniza
- **delta2** = C11 - C13 (BTD 8.4-10.3 μm) - Discriminador de fase
- **delta3** = C07 - C13 (BTD 3.9-10.3 μm) - Contraste térmico

#### 3. Análisis de textura local

Se calcula la media y desviación estándar local (kernel 5×5) de delta1 para identificar patrones espaciales característicos de plumas de ceniza mediante filtros optimizados que manejan valores NaN.

#### 4. Clasificación por condiciones de iluminación

El algoritmo aplica diferentes umbrales según el ángulo cenital solar:

**Noche (SZA > 85°):**
- Alta confianza: delta1 < 0, delta2 > 0, delta3 > 2
- Media confianza: delta1 < 1, delta2 > -0.5, delta3 > 2

**Crepúsculo (70° ≤ SZA ≤ 85°):**
- Similar a noche pero con restricción adicional: C04 > 0.002 y C13 < 273.15K

**Día (SZA < 70°):**
- Similar a noche pero con restricción de reflectancia: C04 > 0.002

#### 5. Refinamiento por umbrales

Solo afectan a la probabilidad alta (HAP) y a la baja (LAP), salvo donde se indica:
- HAP con delta2 ≥ -1 se conserva; con -1.5 ≤ delta2 < -1 pasa a LAP; con delta2 < -1.5 se elimina.
- Clases 1 y 2 con delta3 ≤ 0 se eliminan (incluye la ceniza confirmada por el kernel).
- LAP con delta3 ≤ 1.5 se elimina.

#### 6. Clasificación final por fase de nube

Usando el producto ACTP (Cloud Top Phase):
(Phase: 0 despejado, 1 agua líquida, 2 superenfriada, 3 mixta, 4 hielo, 5 desconocida)
- HAP sobre agua líquida pasa a LAP; HAP sobre hielo se elimina.
- LAP sobre cualquier nube (fase 1 a 5) se elimina.
- La ceniza confirmada no cambia.

La tabla completa de reglas, y las que están en revisión, está en [el plan de octubre de 2026](doc/2026-10-19_plan_mejoras_operacion.md) (P10, P11) y en `tests/test_clasificacion.py`.

### Proyección y georreferenciación

Los datos se procesan en la proyección geoestacionaria nativa del satélite, leída de cada archivo (`goes_imager_projection`). Para GOES-East:

- **Proyección**: Geoestacionaria (GEOS)
- **Altura satelital**: 35,786,023 m sobre el elipsoide
- **Longitud central**: -75.0° (GOES-16 hasta 2025; GOES-19 desde abril de 2025)
- **Elipsoide**: GRS 1980
- **Sistema de barrido**: Eje X

La transformación geoespacial se preserva directamente desde los archivos NetCDF originales usando los atributos de la proyección `goes_imager_projection`.

**Coordenadas lat/lon:** Se calculan automáticamente mediante transformación de la proyección GOES usando `pyproj`, eliminando la necesidad del archivo de navegación (NAV).

**Recorte eficiente:** Cuando se especifica una región de recorte, el sistema:
1. Transforma las coordenadas geográficas del bbox a coordenadas GOES
2. Identifica los índices de píxeles correspondientes
3. Carga únicamente el subconjunto de datos necesario
4. Preserva la resolución y calidad original (sin interpolación)
5. Opcionalmente reproyecta el resultado a EPSG:4326 (lat/lon) al final

Este enfoque minimiza el uso de memoria y acelera significativamente el procesamiento.

## Notas técnicas

- El script determina automáticamente el instante más reciente según la cadencia del dominio:
  - **CONUS**: Minutos terminados en 1 o 6 (ej: 01, 06, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56)
  - **Full Disk**: Múltiplos de 10 (ej: 00, 10, 20, 30, 40, 50)
- Las efemérides (`de421.bsp`) se buscan en `LANOT_SKYFIELD_DIR`; si no está definida, en `/usr/local/share/lanot/skyfield/` si ahí están, y si no, en `~/.cache/lanot_ceniza/`, donde Skyfield las descarga la primera vez
- `LANOT_CENIZA_L2` cambia la carpeta de datos L2 por omisión
- Códigos de salida: 0 bien, 1 error al procesar, 2 argumentos inválidos, 3 faltan datos
- El formato de tiempo en nombres de archivo es `YYYYjjjHHMM` (año, día juliano, hora y minuto UTC)
- El procesamiento usa `np.select()` para clasificaciones eficientes y vectorizadas
- Los filtros espaciales manejan correctamente valores NaN usando métodos optimizados de scipy.ndimage
- La salida GeoTIFF preserva la proyección nativa GOES usando cadenas Proj4 simplificadas
- **Sufijo `_geo`** se agrega automáticamente a los nombres de archivo cuando se reproyecta a EPSG:4326
- **Salida a directorios**: Si `--output` es un directorio, genera nombres automáticos en esa ubicación

### Optimización de rendimiento

- **Kernel vectorizado**: media y desviación estándar locales con filtros uniformes, sin llamadas a Python por píxel ni procesos en paralelo
- **Recorte eficiente**: Los datos se recortan antes de ser procesados, cargando solo la región de interés desde los archivos NetCDF

## Licencia

Ver archivo [LICENSE](LICENSE) para más detalles.

## Contacto

- Alejandro Aguilar Sierra, asierra@unam.mx
- Víctor Manuel Jiménez Escudero, ...

Laboratorio Nacional de Observación de la Tierra (LANOT)

## Operación de baja latencia

El directorio `operacion/` tiene el script, el instalador y el crontab de ejemplo para producir la ceniza CONUS de cada escaneo en un servidor aparte (tahan), con CSPP Geo AIT reducido a lo que necesita el algoritmo. Ver `operacion/README.md`.
