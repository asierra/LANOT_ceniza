# Umbrales configurables por volcán (perfiles)

- **Fecha:** 2026-10-21
- **Estado:** paso 1 hecho (2026-10-23): los perfiles existen y una prueba los compara con el código; `classify_ash` todavía no los lee.

## Por qué

Los umbrales del algoritmo están calibrados para el Popocatépetl. El artículo dice que para otro volcán hay que recalibrarlos y ajustar los límites del ángulo cenital solar a la latitud. Hoy todo está escrito en el código (`classify_ash`, `CLIP_REGIONS`, `FASES_NUBE`), así que cambiar un umbral exige editar el código. El primer caso es un proyecto en Chile, que tiene su propio repositorio.

## Decisiones

1. **Formato TOML**, leído con `tomllib` (biblioteca estándar). Se sube `requires-python` a `>=3.11` (tahan tiene la 3.12).
2. **Los perfiles viven en el repositorio** (`perfiles/popocatepetl.toml`, versionados con el código). `--perfil NOMBRE` elige uno del repositorio y `--perfil RUTA.toml` acepta cualquier archivo. Sin `--perfil` se usa Popocatépetl: la operación no cambia.

## Diseño propuesto

- Un `dataclass` inmutable `Perfil`, leído del TOML, que recibe `classify_ash`.
- Contenido del perfil:
  - umbrales: ΔT1, ΔT2, ΔT3, R1.37, BT13, filtros de ΔT2 y ΔT3, kernel (tamaño y umbral);
  - límites del SZA (70° y 85° para el Popocatépetl);
  - regla de fase como tabla (clase × fase → clase resultante) y fases que cuentan como nube (clase 6);
  - región de recorte, coordenadas del volcán y dominio (CONUS o disco completo).
- Validación estricta: una clave desconocida o faltante es un error.
- El GeoTIFF guarda en sus metadatos el nombre y el hash del perfil.
- Pruebas: el perfil del Popocatépetl reproduce exactamente las pruebas de regresión actuales; pruebas de lectura y de errores del TOML.

## Lo que no se parametriza

La estructura del algoritmo: los tres bloques de iluminación, la fórmula del kernel y el orden de los filtros. Si otro volcán necesita otra lógica (otra banda, otro filtro), es código nuevo con sus pruebas.

## Reunión del 2026-10-23

- Las reglas P10 y P11 y la nube superenfriada quedan como están en el código.
- Solo hay cuatro clases de ceniza: CA, HAP, LAP y sin ceniza. La tabla de fase solo puede dar esas cuatro. Se pueden guardar datos auxiliares, como el 6 (nube), fuera de esas clases.
- No se mostró ningún ejemplo de perfil; se le envían a Víctor los dos archivos de abajo.

## Paso 1 (2026-10-23)

- `perfiles/popocatepetl.toml`: los valores con los que corre la operación, con un comentario por sección. Los umbrales van por bloque de iluminación y por clase, porque no son iguales en todos: BT13 < 273.15 solo está en el HAP del crepúsculo, y R1.37 solo de día y en el HAP del crepúsculo.
- `perfiles/villarrica.toml`: **ejemplo sin calibrar** para el proyecto de Chile. Los umbrales son copia del Popocatépetl; la región es la del proyecto.
- `tests/test_perfiles.py`: valida la estructura (claves de más o de menos son error) y compara un clasificador de referencia, que solo lee el perfil, con `classify_ash` en escenas sintéticas que pasan por cada límite. Se comprobó que cambiar cualquiera de los 50 valores del perfil (umbrales, celdas de la tabla de fase, fases de nube) hace fallar la comparación.
- `requires-python` sube a `>=3.11` por `tomllib`.

### Región

Un nombre predefinido (`recorte = "ashpaper"`) o una lista de puntos `[lon, lat]`: 2 puntos son esquinas opuestas de un rectángulo; 3 o más, un polígono (se recorta el rectángulo que lo contiene y lo de afuera queda en 255). Los pares `[lon, lat]` evitan la confusión de orden: `CLIP_REGIONS` usa `[lon_min, lat_max, lon_max, lat_min]` y lanot-chile `lon_min, lat_min, lon_max, lat_max`.

La zona de Chile es el cuadrilátero que antes venía del shapefile `campo villarrica` de lanot-chile (28° a 47° S, 86° a 45° O); el proyecto deja de usar shapefiles. Los rectángulos de `volcanes.csv` de lanot-chile son de `ash.py`, que ya no se usa.

**Corrección pendiente del recorte:** `process_instant` pasa a la proyección GOES solo dos esquinas (SO y NE). En esa proyección el rectángulo se deforma y se puede perder una franja; lanot-chile ya transforma las cuatro. Hay que transformar las cuatro esquinas y puntos a lo largo de los bordes. En el Popocatépetl la diferencia es de uno o dos píxeles; en Chile, a 40° S y en disco completo, puede ser mayor. Va en un commit aparte.

## Plan para usar los perfiles y regiones de más de dos esquinas (2026-10-23)

Cuatro commits separados. Los tres primeros no cambian la operación del Popocatépetl.

### 1. Regiones como lista de puntos y recorte con bordes densificados

- Toda región es una lista de puntos `[lon, lat]`: `CLIP_REGIONS` pasa a 2 puntos por región y `--clip` sigue aceptando sus nombres.
- `process_instant` transforma a la proyección GOES todos los vértices y puntos intermedios de cada borde, y toma el mínimo y máximo de x, y (hoy solo transforma las esquinas SO y NE, `detect_ash.py:700-708`). Un vértice fuera del disco visible es error.
- La reproyección a lat/lon usa el rectángulo que contiene a la región, no un `bbox` de 4 números.
- Las pruebas de regresión no usan recorte. Se comprueba con escaneos reales en tahan que la salida de `ashpapergeo` no cambia (ya hay un margen de 10 % antes de reproyectar).

### 2. `classify_ash` con perfil

- `carga_perfil(nombre o ruta)` en `detect_ash.py`, con la validación estricta que hoy está en `tests/test_perfiles.py`. Opción `--perfil`; sin ella, `popocatepetl`.
- `classify_ash` recibe el perfil y deja de tener números escritos; `FASES_NUBE` y `kernel_size` salen del perfil.
- Las pruebas de regresión deben dar los mismos píxeles. El clasificador de referencia de `test_perfiles.py` se retira: la prueba compara `classify_ash` con perfiles modificados.
- El GeoTIFF guarda el nombre y el hash del perfil.
- **Instalación:** el wheel solo incluye `detect_ash.py` y `compare_ash.py`, así que `instala.sh` no copiaría `perfiles/` a `/opt/lanot/ceniza`. Incluir la carpeta en el paquete (`pyproject.toml`) y buscar los perfiles relativos al módulo.

### 3. Polígonos y `--geo`

- Con 3 o más puntos, después de clasificar (para que el kernel cerca del borde vea a sus vecinos reales), lo que queda fuera del polígono pasa a 255, con `rasterio.features.geometry_mask` sobre la malla de salida (GOES o lat/lon). Los bordes del polígono son rectos en lat/lon y se densifican al transformarlos.
- Opción `--geo` para reproyectar a lat/lon una región dada con puntos, que no tiene nombre. El sufijo `geo` de `--clip` (`ashpapergeo`) sigue funcionando.
- `--clip` manda sobre la región del perfil, así `procesa_ceniza.sh` no cambia.
- Prueba con el cuadrilátero de `perfiles/villarrica.toml` sobre una escena sintética.

### 4. Dominio del perfil (disco completo, para Chile)

Se puede dejar para cuando se arme lo de Chile.

- `main` llama a `get_moment()` sin dominio: sin `-m` calcula el instante como CONUS. Usar el dominio del perfil.
- Los rangos de instantes y el reporte de fallas usan 5 min; el disco completo es cada 10 min.
- `procesa_ceniza.sh` es una cadena solo CONUS (L1b de `conus`, CSPP en ese dominio). Una cadena de disco completo es trabajo aparte, probablemente del repo nuevo de Chile.
- La resolución de la salida en lat/lon está fija en 0.02°; podría pasar al perfil.

## Pendiente

- Preguntar a Víctor qué valores cambian de un volcán a otro, y si basta un solo par de límites del SZA para una zona de 19° de latitud.
