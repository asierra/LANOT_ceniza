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
- **NAV**: Navegación (Latitud/Longitud)

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
- **rioxarray**: Extensión de xarray para operaciones geoespaciales
- **numpy**: Operaciones numéricas y manejo de arrays
- **scipy**: Filtros y operaciones de procesamiento de imágenes (ndimage)
- **skyfield**: Cálculos astronómicos precisos (posición del Sol, efemérides JPL)
- **pyproj**: Transformaciones de sistemas de coordenadas y proyecciones
- **dateutil**: Parsing de fechas en formato ISO 8601
- **pathlib**: Manejo moderno de rutas de archivos

## Uso

### Ejecución básica

Procesar el momento más reciente automáticamente:

```bash
./detect_ash.py
```

Procesar un momento específico:

```bash
./detect_ash.py --path /data/ceniza/2019/spring --moment 20191001731
```

Especificar archivo de salida personalizado:

```bash
./detect_ash.py --path /data/ceniza/2019/spring --moment 20191001731 --output resultado_ceniza.tif
```

### Parámetros de línea de comandos

- `--path`: Ruta al directorio que contiene los archivos NetCDF L2 (por defecto: `/data/ceniza/2019/spring`)
- `--moment`: Momento a procesar en formato `YYYYjjjHHMM` (año, día juliano, hora y minuto). Si no se especifica, se calcula automáticamente el más reciente
- `--output`: Ruta del archivo GeoTIFF de salida. Si no se especifica, se genera como `ceniza_[momento].tif`

### Salida

El script genera un archivo GeoTIFF con la clasificación de ceniza volcánica en proyección geoestacionaria GOES-16. Los valores en el raster representan:

- **0**: Sin detección
- **1**: Ceniza volcánica - alta confianza (BTD clásica)
- **2**: Ceniza volcánica - media confianza
- **3**: Ceniza volcánica refinada (umbral delta2)
- **4**: Nube de agua reclasificada
- **5**: Ceniza sobre superficie fría

El archivo incluye georreferenciación completa y puede ser visualizado en cualquier software GIS (QGIS, ArcGIS, etc.).

## Estructura del proyecto

```
LANOT_ceniza/
├── detect_ash.py       # Script principal
├── requirements.txt    # Dependencias del proyecto
├── de421.bsp          # Efemérides planetarias (descargado automáticamente)
├── README.md          # Este archivo
└── LICENSE            # Licencia del proyecto
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

## Notas técnicas

- El script determina automáticamente el momento más reciente según la cadencia del dominio:
  - **CONUS**: Minutos terminados en 1 o 6 (ej: 01, 06, 11, 16, 21, 26, 31, 36, 41, 46, 51, 56)
  - **Full Disk**: Múltiplos de 10 (ej: 00, 10, 20, 30, 40, 50)
- Los archivos de efemérides (de421.bsp) se descargan automáticamente por Skyfield la primera vez
- El formato de tiempo en nombres de archivo es `YYYYjjjHHMM` (año, día juliano, hora y minuto UTC)
- El procesamiento usa `np.select()` para clasificaciones eficientes y vectorizadas
- Los filtros espaciales manejan correctamente valores NaN usando métodos optimizados de scipy.ndimage
- La salida GeoTIFF preserva la proyección nativa GOES usando cadenas Proj4 simplificadas

## Licencia

Ver archivo [LICENSE](LICENSE) para más detalles.

## Contacto

- Alejandro Aguilar Sierra, asierra@unam.mx
- Víctor Manuel Jiménez Escudero, ...

Laboratorio Nacional de Observación de la Tierra (LANOT)
