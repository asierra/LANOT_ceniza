# Refactorización de detect_ash.py

Actúa como un Ingeniero de Software experto en Python, HPC y procesamiento de datos satelitales. 

## Contexto
El script `detect_ash.py` lee archivos NetCDF de GOES L2, aplica un algoritmo de clasificación de ceniza volcánica y exporta un GeoTIFF de 1 banda (uint8) con una tabla de colores incrustada. El código actual es estable y funciona correctamente, pero necesita 4 mejoras específicas orientadas a la limpieza, el manejo de errores y la modularidad para su paso a producción.

## Tareas Específicas
Por favor, refactoriza el código aplicando estrictamente los siguientes 4 cambios:

### 1. Caché centralizado para Skyfield
Actualmente `load('de421.bsp')` y `load.timescale()` descargan archivos en el directorio de ejecución. 
*   **Acción:** Crea un objeto `Loader` apuntando a `/usr/local/share/lanot/skyfield` y úsalo para cargar tanto las efemérides como el timescale. El patrón correcto es:
    ```python
    loader = Loader('/usr/local/share/lanot/skyfield')
    eph_global = loader('de421.bsp')
    ts_global = loader.timescale()
    ```
    No uses `load.Loader` (atributo incorrecto); la clase se importa directamente de `skyfield.api` como `from skyfield.api import Loader`.
*   Asegúrate de crear el directorio si no existe usando `Path('/usr/local/share/lanot/skyfield').mkdir(parents=True, exist_ok=True)` **antes** de instanciar el `Loader`.

### 2. Declaración explícita de NoData en rioxarray
*   **Acción:** Justo después de las líneas `output_da.rio.write_crs(...)` y `output_da.rio.write_transform(...)` (líneas ~930-931), añade la línea `output_da.rio.write_nodata(255, inplace=True)` antes del bloque `if bbox and reproject_to_geo`.

### 3. Mejora en el manejo de excepciones (Logging)
En el bloque `try/except` principal de la función `main` (aprox. línea 957), actualmente se usa `logger.error` seguido de `import traceback; traceback.print_exc()`.
*   **Acción:** Reemplaza esto utilizando exclusivamente `logger.exception(f"\n*** Error crítico procesando instante {instant_str}:")`, eliminando la importación manual y uso de `traceback`.

### 4. Modularización del Motor Científico
La función `process_instant` es demasiado larga porque mezcla operaciones I/O con la lógica matemática.
*   **Acción:** Extrae toda la lógica matemática de clasificación a una nueva función pura llamada `classify_ash`. El bloque a extraer comprende, dentro de `process_instant`, desde el cálculo de las deltas BTD (`delta1 = c13 - c15`, etc.) hasta el último `ceniza[~valid_data_mask] = 255` inclusive (líneas ~834-906 en la versión actual).
*   **Firma correcta:** `def classify_ash(c04, c07, c11, c13, c15, phase, sza, valid_data_mask, kernel_size=5) -> np.ndarray:`
    *   **No incluyas `c14`**: ese array sólo se usa antes de este bloque para actualizar `valid_data_mask` y no interviene en ningún cálculo matemático de la clasificación.
    *   `valid_data_mask` es un **parámetro de entrada** (ya está calculado antes de llamar a esta función); no es un valor producido por ella.
*   **Retorno esperado:** Devuelve únicamente `ceniza` (el array `np.ndarray` uint8 con nodata=255 ya aplicado).
*   Actualiza `process_instant` para que llame a la función así:
    ```python
    ceniza = classify_ash(c04, c07, c11, c13, c15, phase, sza, valid_data_mask)
    ```

## Restricciones Críticas
*   **NO** alteres la lógica matemática de los índices de ceniza ni las condiciones de `np.select`.
*   **NO** alteres la sección final de guardado con `rasterio` (configuración de bandas, uint8, nodata y write_colormap).
*   **NO** modifiques la función `get_filelist_from_path` ni la búsqueda de archivos.

## Salida Esperada
Por favor, genera el código completo refactorizado para poder reemplazar el contenido actual del archivo `detect_ash.py`.
