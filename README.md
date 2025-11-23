# LANOT_ceniza

Sistema de detección de ceniza volcánica del Popocatépetl utilizando datos del satélite GOES-16 (ABI).

## Descripción

Este proyecto procesa datos de nivel 2 (L2) del instrumento ABI (Advanced Baseline Imager) del satélite GOES-16 para detectar y analizar ceniza volcánica emitida por el volcán Popocatépetl. 

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

- Python 3.8 o superior
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

4. **Instalar las dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

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
- **Pillow (PIL)**: Generación de imágenes PNG a color
- **aggdraw**: Dibujo de vectores de alta calidad sobre imágenes PNG
- **pyshp**: Lectura de archivos shapefile para mapas base

### Instalación de MapDrawer (CLI)

Para utilizar la herramienta de dibujo de mapas `mapdrawer.py` como un comando del sistema (`mapdrawer`), sigue estos pasos:

1. **Hacer ejecutable el script:**
   ```bash
   chmod +x mapdrawer.py
   ```

2. **Crear un enlace simbólico (requiere permisos de administrador):**
   ```bash
   sudo ln -s $(pwd)/mapdrawer.py /usr/local/bin/mapdrawer
   ```

3. **Verificar la instalación:**
   ```bash
   mapdrawer --help
   ```

## Uso

### Detección de Ceniza (detect_ash.py)

### Ejecución básica

Procesar el momento más reciente automáticamente:

```bash
./detect_ash.py
```

Procesar un momento específico:

```bash
./detect_ash.py --path /data/ceniza/2019/spring --moment 20191001731
```

Especificar archivo o directorio de salida:

```bash
# Nombre de archivo específico
./detect_ash.py --moment 20191001731 --output resultado_ceniza.tif

# Directorio (genera nombre automático: ceniza_20191001731.tif)
./detect_ash.py --moment 20191001731 --output /data/resultados/

# Con reproyección, el sufijo _geo se agrega automáticamente
./detect_ash.py --moment 20191001731 --clip popocatepetlgeo --output /data/resultados/
# Genera: /data/resultados/ceniza_20191001731_geo.tif
```

### Parámetros de línea de comandos

- `--path`: Ruta al directorio que contiene los archivos NetCDF L2 (por defecto: `/data/ceniza/2019/spring`)
- `--moment`: Momento a procesar en formato `YYYYjjjHHMM` (año, día juliano, hora y minuto). Si no se especifica, se calcula automáticamente el más reciente
- `--output`: Ruta de salida para el GeoTIFF. Puede ser:
  - **Un archivo**: `resultado.tif` - Guarda con ese nombre
  - **Un directorio**: `/data/salida/` - Genera automáticamente `ceniza_[momento].tif` (o con sufijo `_geo` si se reproyecta)
  - **Por defecto**: `./ceniza_[momento].tif`
- `--clip`: Región para recortar el resultado. Opciones disponibles:
  - `centromex`: Centro de México (proyección GOES nativa)
  - `centromexgeo`: Centro de México (reproyectado a lat/lon EPSG:4326)
  - `popocatepetl`: Región del Popocatépetl (proyección GOES nativa)
  - `popocatepetlgeo`: Región del Popocatépetl (reproyectado a lat/lon EPSG:4326)
- `--png`: Genera también una imagen PNG a color con mapa base, fecha/hora y logo LANOT

### Ejemplos de uso

**Procesamiento completo sin recorte:**
```bash
./detect_ash.py --path /data/ceniza/2019/spring --moment 20190871402
```

**Generar también imagen PNG a color:**
```bash
./detect_ash.py --moment 20190871402 --png
```

**Recorte a región específica (proyección GOES):**
```bash
./detect_ash.py --moment 20190871402 --clip centromex
./detect_ash.py --moment 20190871402 --clip popocatepetl --png
```

**Recorte con reproyección a coordenadas geográficas:**
```bash
./detect_ash.py --moment 20190871402 --clip centromexgeo --png
./detect_ash.py --moment 20190871402 --clip popocatepetlgeo --output /data/salida/ --png
```

**Guardar múltiples archivos en un directorio:**
```bash
# El directorio puede especificarse solo una vez
./detect_ash.py --moment 20190871402 --output /data/procesados/ --png
./detect_ash.py --moment 20190871506 --output /data/procesados/ --png
# Genera: ceniza_20190871402.tif, ceniza_20190871402.png, ceniza_20190871506.tif, etc.
```

### Regiones de recorte predefinidas

- **centromex**: [-107.23, 22.72, -93.84, 14.94] (lon_min, lat_max, lon_max, lat_min)
- **popocatepetl**: [-100.26, 20.58, -96.85, 18.29]

El recorte se realiza **antes** de procesar los datos, mejorando significativamente el rendimiento y reduciendo el uso de memoria.

### Rendimiento

El sistema está optimizado para procesamiento paralelo en servidores con múltiples cores:

- **Dominio completo CONUS** (~5000x3000 píxeles): **~8 segundos** en servidor con 64 cores
- **Recortes regionales** (< 1M píxeles): Procesamiento secuencial optimizado
- **Paralelización automática**: Detecta y utiliza cores disponibles (deja 2 libres por defecto)
- **Escalabilidad**: El rendimiento mejora linealmente con el número de cores disponibles

El procesamiento paralelo se aplica automáticamente a la operación más costosa (cálculo de desviación estándar local) cuando el dominio es lo suficientemente grande.

### Salida

El script genera un archivo GeoTIFF con la clasificación de ceniza volcánica en proyección geoestacionaria GOES-16 (o EPSG:4326 si se reproyecta). Los valores en el raster representan:

- **0**: Sin detección (negro en PNG)
- **1**: Ceniza volcánica - alta confianza (rojo en PNG)
- **2**: Ceniza volcánica - media confianza (naranja en PNG)
- **3**: Ceniza volcánica refinada - umbral delta2 (amarillo en PNG)
- **4**: Nube de agua reclasificada (verde en PNG)
- **5**: Ceniza sobre superficie fría (azul en PNG)

El archivo incluye georreferenciación completa y puede ser visualizado en cualquier software GIS (QGIS, ArcGIS, etc.).

**Salida PNG (opcional con `--png`):**

Cuando se usa el parámetro `--png`, se genera también una imagen PNG a color con las mismas dimensiones que el GeoTIFF. La imagen incluye:

- **Clasificación de ceniza** con colores definidos en `ash.cpt`:
  - Rojo: Ceniza volcánica de alta confianza
  - Naranja: Ceniza probable
  - Amarillo: Ceniza menos probable
  - Verde: Nubes de agua
  - Azul: Ruido/superficie fría
  - Negro: Sin detección

- **Mapa base** dibujado con MapDrawer (si está disponible `/usr/local/share/lanot`):
  - Líneas costeras (blanco)
  - Fronteras nacionales (blanco)
  - Estados de México (blanco)
  - **Logo LANOT** en esquina superior derecha
  - **Fecha/hora** en esquina inferior izquierda (formato: "2019/10/10 17:31Z")
    - Usa fuente monoespaciada DejaVuSansMono para mantener posición fija en animaciones

La imagen PNG calcula automáticamente los límites geográficos del raster (ya sea en proyección GOES o reproyectado a lat/lon) y dibuja el mapa base en las coordenadas correctas.

> **Nota**: Para que MapDrawer funcione correctamente, se requieren los archivos shapefile en `/usr/local/share/lanot/shapefiles/` y el logo en `/usr/local/share/lanot/logos/`. Si estos recursos no están disponibles, el PNG se generará solo con la clasificación de ceniza.

**Nombres de archivo con sufijo `_geo`:**

Cuando se usa reproyección a coordenadas geográficas (opciones que terminan en "geo"), los archivos de salida incluyen automáticamente el sufijo `_geo`:

```bash
# Sin reproyección
./detect_ash.py --moment 20191001731
# Genera: ceniza_20191001731.tif

# Con reproyección
./detect_ash.py --moment 20191001731 --clip popocatepetlgeo
# Genera: ceniza_20191001731_geo.tif

# Con PNG
./detect_ash.py --moment 20191001731 --clip popocatepetlgeo --png
# Genera: ceniza_20191001731_geo.tif y ceniza_20191001731_geo.png
```

### Dibujado de Mapas (mapdrawer)

La herramienta `mapdrawer` permite dibujar mapas base, logos, fechas y leyendas sobre imágenes existentes desde la línea de comandos.

#### Ejecución básica

```bash
mapdrawer imagen_entrada.png --output imagen_salida.png --crs goes16 --recorte centromex
```

#### Parámetros principales

- `input_image`: Ruta de la imagen de entrada (obligatorio).
- `--output`: Ruta de salida (opcional, por defecto sobreescribe).
- `--crs`: Sistema de coordenadas de la imagen. Soporta claves cortas (`goes16`, `goes17`, `goes18`) o códigos EPSG (`epsg:4326`).
- `--bounds`: Límites geográficos manuales (ulx uly lrx lry).
- `--recorte`: Nombre de un recorte predefinido (ej: `centromex`, `Mexico`).
- `--layer`: Capa a dibujar en formato `NOMBRE:COLOR:GROSOR`. Se puede repetir.
  - Ej: `--layer COASTLINE:cyan:0.5 --layer MEXSTATES:white:1.0`
- `--logo-pos`: Posición del logo (0-3).
- `--timestamp`: Texto de fecha/hora.
- `--cpt`: Archivo de paleta de colores para generar leyenda.

#### Ejemplo completo

```bash
mapdrawer ceniza.png \
  --crs goes16 \
  --recorte centromex \
  --layer COASTLINE:cyan:0.5 \
  --layer MEXSTATES:white:1.0 \
  --logo-pos 1 \
  --timestamp "2023/11/23 12:00 UTC" \
  --cpt ash.cpt
```

## Estructura del proyecto

```
LANOT_ceniza/
├── detect_ash.py       # Script principal de detección
├── mapdrawer.py        # Módulo para dibujar mapas base en PNG
├── requirements.txt    # Dependencias del proyecto
├── ash.cpt             # Paleta de colores para clasificación
├── de421.bsp          # Efemérides planetarias (descargado automáticamente)
├── README.md          # Este archivo
└── LICENSE            # Licencia del proyecto
```

### Recursos adicionales para MapDrawer (opcional)

Para generar imágenes PNG con mapa base, se requiere la siguiente estructura en `/usr/local/share/lanot`:

```
/usr/local/share/lanot/
├── shapefiles/
│   ├── ne_10m_coastline.shp         # Líneas costeras
│   ├── ne_10m_admin_0_countries.shp # Fronteras nacionales
│   └── dest_2015gwLines.shp         # Estados de México
└── logos/
    └── lanot_negro_sn-128.png       # Logo LANOT
```

Los shapefiles pueden descargarse de:
- [Natural Earth - 10m Coastline](https://www.naturalearthdata.com/downloads/10m-physical-vectors/)
- [Natural Earth - 10m Admin 0 - Countries](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/)
- Estados de México: `dest_2015gwLines.shp` (shapefile de estados de México de INEGI)

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

- Reclasificación basada en delta2 ≥ -1.5 para ceniza refinada
- Eliminación de falsos positivos usando delta3 ≤ 0 o delta3 ≤ 1.5

#### 6. Clasificación final por fase de nube

Usando el producto ACTP (Cloud Top Phase):
- Reclasifica ceniza media confianza detectada sobre nubes de agua (Phase=1) 
- Elimina detecciones sobre polvo (Phase=4)
- Refina ceniza sobre hielo (Phase≥2)

### Proyección y georreferenciación

Los datos se procesan en la proyección geoestacionaria nativa GOES-16:

- **Proyección**: Geoestacionaria (GEOS)
- **Altura satelital**: 35,786,023 m sobre el elipsoide
- **Longitud central**: -75.0° (GOES-16 East)
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

- El script determina automáticamente el momento más reciente según la cadencia del dominio:
  - **CONUS**: Minutos terminados en 1 o 6 (ej: 01, 06, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56)
  - **Full Disk**: Múltiplos de 10 (ej: 00, 10, 20, 30, 40, 50)
- Los archivos de efemérides (de421.bsp) se descargan automáticamente por Skyfield la primera vez
- El formato de tiempo en nombres de archivo es `YYYYjjjHHMM` (año, día juliano, hora y minuto UTC)
- El procesamiento usa `np.select()` para clasificaciones eficientes y vectorizadas
- Los filtros espaciales manejan correctamente valores NaN usando métodos optimizados de scipy.ndimage
- La salida GeoTIFF preserva la proyección nativa GOES usando cadenas Proj4 simplificadas
- **Sufijo `_geo`** se agrega automáticamente a los nombres de archivo cuando se reproyecta a EPSG:4326
- **Salida a directorios**: Si `--output` es un directorio, genera nombres automáticos en esa ubicación
- **Fuente monoespaciada** en PNG (DejaVuSansMono) mantiene la fecha fija para animaciones suaves

### Optimización de rendimiento

- **Procesamiento paralelo automático**: El cálculo de desviación estándar local (operación más costosa) se paraleliza automáticamente en sistemas con múltiples cores
- **Recorte eficiente**: Los datos se recortan antes de ser procesados, cargando solo la región de interés desde los archivos NetCDF
- **Umbral de paralelización**: Arrays con >1M píxeles utilizan procesamiento paralelo; arrays menores usan procesamiento secuencial optimizado
- **Gestión de recursos**: Por defecto, el sistema utiliza todos los cores disponibles menos 2 (reservados para el sistema operativo)
- **División inteligente**: El array se divide en bloques horizontales con overlap para evitar artefactos en los bordes

El rendimiento escala linealmente con el número de cores disponibles, permitiendo procesamiento casi en tiempo real en servidores de alto rendimiento.

## Licencia

Ver archivo [LICENSE](LICENSE) para más detalles.

## Contacto

- Alejandro Aguilar Sierra, asierra@unam.mx
- Víctor Manuel Jiménez Escudero, ...

Laboratorio Nacional de Observación de la Tierra (LANOT)
