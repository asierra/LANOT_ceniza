# CLAUDE.md

Detección de ceniza volcánica del Popocatépetl con datos L2 del ABI de GOES-East. La descripción completa está en `README.md`; aquí va lo necesario para trabajar en el código.

## Idioma

Todo el proyecto está en español: código (nombres nuevos, comentarios, docstrings, mensajes), documentación y mensajes de commit. Hay nombres heredados en inglés (`classify_ash`, `process_instant`, `CLIP_REGIONS`); no se renombran sin motivo.

## Comandos

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[pruebas]'
pytest                                # todas las pruebas
pytest tests/test_perfiles.py -k nombre
ACTUALIZA_ESPERADOS=1 pytest tests/test_regresion.py   # regenera los GeoTIFF esperados
```

Python ≥ 3.11 (`tomllib`). En tahan, la operación usa el Python 3.12 del sistema.

## Estructura

- `detect_ash.py`: todo el algoritmo, en un módulo suelto en la raíz (no es un paquete). Se instala como `lanot-detect-ash`. Las piezas principales son:
  - `carga_perfil` / `Perfil`: leen y validan los umbrales del TOML;
  - `get_sun_zenith_angle`: el ángulo cenital solar, con Skyfield y DE421;
  - `classify_ash`: la clasificación;
  - `process_instant`: lectura, recorte, reproyección y escritura del GeoTIFF;
  - `main`: la línea de comandos.
- `perfiles/*.toml`: umbrales, tabla de fase y región por volcán. `popocatepetl.toml` es el de omisión y el que usa la operación. `villarrica.toml` es un ejemplo sin calibrar. Se instalan con el paquete (`pyproject.toml`, `include`).
- `operacion/`: cadena de baja latencia en tahan (CSPP Geo y luego `lanot-detect-ash --clip ashpapergeo`). Se instala en `/opt/lanot/ceniza` con `operacion/instala.sh`. Ver `operacion/README.md`.
- `herramientas/`:
  - `corre_version.sh` y `compara_salidas.py` comparan las salidas de dos commits (`compara_salidas.py` lee también los GeoTIFF de TeraScan);
  - `reglas_terascan.py` aplica las reglas de TeraScan y `classify_ash` a los mismos L2; `compara_terascan.py` dibuja el mapa de diferencias de un instante (requiere matplotlib);
  - `genera_fixture.py` recorta NetCDF para las pruebas.
  No se instalan con el paquete.
- `tests/`: la regresión (`test_regresion.py`) corre tres instantes reales recortados (noche, crepúsculo y día) de `tests/datos/l2` y compara contra `tests/datos/esperado`.
- `doc/`: registro de decisiones (ver abajo).
- `paper/`: artículo (Journal of Applied Volcanology) y borrador para SoftwareX/JOSS.

Las efemérides `de421.bsp` no se versionan. Se buscan en `LANOT_SKYFIELD_DIR`, luego en `/usr/local/share/lanot/skyfield` y luego en `~/.cache/lanot_ceniza`. Si no están, Skyfield las descarga.

## Salida

GeoTIFF de una banda uint8 con:
- 0: sin ceniza;
- 1: CA;
- 2: HAP;
- 3: LAP;
- 6: nube (dato auxiliar);
- 255: sin datos.

El 4 y el 5 están reservados. Junto al GeoTIFF va su `.qml`. Las clases de ceniza son solo cuatro (CA, HAP, LAP y sin ceniza); lo demás es auxiliar.

## Reglas

- **La salida del Popocatépetl no cambia sin querer.** Las pruebas de regresión y `tests/test_perfiles.py` tienen que pasar. Si un cambio altera la salida a propósito, se regeneran los esperados y el commit explica la diferencia. Para cambios del algoritmo, comparar versiones con `herramientas/corre_version.sh` y `compara_salidas.py`.
- **Umbrales en el perfil, no en el código.** Lo configurable vive en `perfiles/*.toml`. La validación es estricta: una clave de más o de menos es error. La estructura del algoritmo (bloques de iluminación, kernel, orden de los filtros) no se parametriza; otro algoritmo es código nuevo con sus pruebas.
- **Regiones como puntos `[lon, lat]`:** con 2 puntos son esquinas opuestas; con 3 o más, un polígono, y lo que queda fuera se marca 255.
- La operación en tahan depende de este repositorio. Un cambio que afecte la instalación (archivos nuevos que deban instalarse, dependencias, opciones de línea de comandos) se refleja en `operacion/` y en su README.

## Decisiones y pendientes

`doc/` guarda un archivo por plan o decisión, `AAAA-MM-DD_tema.md`, que empieza con su fecha y su estado. `doc/README.md` es el índice con el estado de cada uno. Al terminar un paso de un plan, se actualizan el estado en el documento y en el índice. El estado actual del proyecto está en ese índice.

## Commits

Mensaje corto en español con prefijo del área: `detect_ash:`, `perfiles:`, `recorte:`, `operación:`, `doc:`, `paper:`, `pruebas:`, `README:`. Un cambio por commit.
