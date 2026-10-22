# Plan de mejoras para la operación de `detect_ash.py`

- **Fecha:** 2026-10-19
- **Estado:** aprobado el 2026-10-19. Fases 0, 1 y 2 implementadas el 2026-10-19 y 20 (ver "Seguimiento" al final). Fase 3 (P10, P11) pendiente de decisión con el autor principal.
- **Rama:** `operacion-tahan`

## Contexto

El código no se revisaba desde mayo de 2026 (refactorización) y la parte científica no ha cambiado desde diciembre de 2025. Ahora corre en operación en tahan cada 5 minutos (`operacion/procesa_ceniza.sh`, desde el 2026-10-18). Este plan busca que la **operación** sea correcta, rápida y vigilable. No busca cambiar el artículo: para la revisión solo se pidió la latencia, que ya se midió.

**Versiones de referencia:**

| nombre | commit | dónde | uso |
|---|---|---|---|
| diciembre | `90ad79f` (2025-12-06; ciencia idéntica a `c93d979`) | `tahan:/opt/LANOT_ceniza.old` | produjo los resultados del artículo |
| mayo | `9dd4752` (2026-05-04) | `tahan:/opt/LANOT_ceniza` | refactorización + "igualar terascan" |
| operación | `feb5241` (al empezar); `286a509` (instalada el 2026-10-20, ~01:20 UTC) | `tahan:/opt/lanot/ceniza` | la ciencia de mayo al empezar; con este plan, las fases 0 a 2 |

Datos para comparar: en tahan siguen las entradas L2 del 2024-02-27 (`/data/ceniza/l2/2024/02/27`) y las 168 salidas de diciembre (`/data/ceniza/output/20240227`). Para 2019 y 2023 también hay entradas en `/data/ceniza/l2`.

**Muestra usada en las comparaciones ("63 escenas"):** CONUS completo, copiado de tahan: 2024-02-27 (cada hora, y cada 5 min de 03:00 a 04:56 UTC, con ceniza de noche) y 2019-03-01 de 11:02 a 15:02 UTC cada 15 min (amanecer, crepúsculo y día; con duplicados CG_/OR_). En total, 236 millones de píxeles.

## Orden propuesto

Primero la herramienta de comparación, porque con ella se evalúan todos los demás cambios. Después, los cambios que **no deben** alterar la clasificación, y al final los que **sí** la alteran, uno por commit, cada uno con su comparación.

| fase | puntos | ¿cambia la clasificación? |
|---|---|---|
| 0 | P0 comparación y pruebas de regresión | no |
| 1 | P1 kernel vectorizado, P2 búsqueda de archivos, P3 rutas configurables, P4 reporte de fallas, P5 limpieza y doc/ | no (P1: diferencias de redondeo, se miden) |
| 2 | P6 SZA, P7 valor de "sin ceniza", P8 límites del crepúsculo, P9 C14 | sí, poco; se mide |
| 3 | P10 regla de fase, P11 filtro ΔT3 sobre ceniza confirmada | sí; **requiere decisión** con el autor principal |

---

## Fase 0

### P0. Comparación de versiones y pruebas de regresión

**Por qué.** No hay pruebas. Sin una forma reproducible de comparar dos versiones, cualquier cambio a la ciencia es a ciegas.

**Qué.**
- `herramientas/corre_version.sh` corre cualquier commit (o el árbol de trabajo) sobre una lista de instantes, y `herramientas/compara_salidas.py` compara dos carpetas de salidas y reporta por clase: píxeles que cambian, matriz de confusión 0/1/2/3/255 y escaneos con ceniza que aparecen o desaparecen. La salida de diciembre es RGBA; se decodifica a clases por color (rojo = 1, naranja = 2, amarillo = 3, transparente = 0 o sin datos).
- Pruebas con `pytest`:
  - **Unitarias** de `classify_ash` con arreglos sintéticos pequeños, un caso por regla (cada umbral, cada bloque de iluminación, cada regla de fase). Documentan la regla y detectan cambios accidentales.
  - **Regresión** con un recorte pequeño de un caso real (por ejemplo, 2019-03-01, el de la animación), con la salida esperada guardada en el repo (unos KB).
- La comparación grande (escenas CONUS completas) se corre a mano, con datos copiados de tahan. No va en las pruebas.

**Resultado.** 85 pruebas (`pytest`), con recortes de 122×178 píxeles de tres casos reales: noche (2024-02-27 04:06), crepúsculo (2019-03-01 13:32) y día (14:37). `herramientas/genera_fixture.py` hace los recortes. La versión de diciembre también se puede correr (con módulos vacíos en lugar de PIL y mapdrawer).

**Riesgo.** Ninguno; no toca la operación.

---

## Fase 1: sin cambio en la clasificación

### P1. Kernel estadístico vectorizado

**Por qué.** La desviación estándar local usa `ndimage.generic_filter(np.nanstd)`, que llama a Python por cada píxel. En CONUS tarda 7.3 s con 16 procesos, casi todo el paso de ceniza.

**Qué.** Calcular media y desviación con `uniform_filter` sobre x, x² y el conteo de valores válidos (en float64), con var = E[x²] − E[x]². Se eliminan el `ProcessPoolExecutor`, la opción `--jobs` y la variable `LANOT_CENIZA_JOBS`. Las dos se agregaron el 2026-10-18 (`4132e64`) solo para limitar los procesos del kernel en tahan; únicamente las usa `procesa_ceniza.sh` (no el crontab), que se ajusta en el mismo commit. No hay nada que mantener por compatibilidad.

**Medido (2026-10-19, en tahan, arreglo de 1500×2500 con 5 % de NaN):** 7.30 s con 16 procesos contra 0.17 s con 1 proceso. Diferencia máxima de 2e-7; los NaN coinciden.

**Verificación.** Con P0, en días completos. Se espera clasificación idéntica, salvo píxeles justo en un umbral (diferencia de redondeo); se cuentan.

**Efecto en la operación.** Se liberan 16 núcleos de tahan para la cadena polar.

**Resultado.** 0 píxeles distintos en las 63 escenas; 2.6 s por escena contra ~45 s antes (6 núcleos, aquí). En tahan, el paso de ceniza (recorte `ashpapergeo`) bajó de 9.2 s a **1.0 s**, y la latencia total de ~4.5 a **~4.3 min** (desde el 2026-10-20 00:41 UTC).

### P2. Búsqueda de archivos con expresión regular estricta

**Por qué.** `get_filelist_from_path` acepta un archivo si `'C04' in nombre`, lo que también deja pasar L1b (`RadC-M6C04`), PACUS (`CMIPP`) u otros satélites. Y `process_instant` vuelve a asociar archivos a productos con otra regla distinta. Además, si hay duplicados, el elegido depende del orden del sistema de archivos.

**Qué.** Una sola función con una expresión regular por producto, por ejemplo `^(OR|CG)_ABI-L2-CMIPC-M\dC04_G\d{2}_s(\d{11})`. Se agrega la detección del satélite (G16/G19) y se exige que todos los archivos sean del mismo satélite y dominio (C = CONUS, F = disco completo). Los duplicados se resuelven de forma determinista (CG_ antes que OR_, y luego la fecha de creación `_c` más reciente).

**Verificación.** Pruebas unitarias con listas de nombres reales (M3, M6, G16, G19, CG_, OR_, L1b mezclados) y `--dry-run` sobre la muestra de 2019 y 2024: mismo número de instantes completos que antes (63 de 63). 2023 no se revisó.

### P3. Rutas configurables

**Por qué.** `/usr/local/share/lanot/skyfield` está fija y además se intenta crear (`mkdir`), lo que falla por permisos fuera de LANOT. El paquete se anuncia como código abierto. `/data/ceniza/l2` también está fija como entrada por omisión.

**Qué.** Variables de entorno `LANOT_SKYFIELD_DIR` (por omisión la ruta actual si existe; si no, el caché de usuario `~/.cache/lanot_ceniza`) y `LANOT_CENIZA_L2`. Sin `mkdir` en rutas del sistema. Un mensaje claro si falta `de421.bsp` (o se descarga en el caché de usuario).

**Resultado.** Implementado así; pruebas en `tests/test_rutas.py`. En tahan sigue usando `/usr/local/share/lanot/skyfield`.

### P4. Reporte de fallas

**Por qué.** Hoy las fallas no se ven:
- `lanot-detect-ash` termina con código 0 aunque falten archivos o el procesamiento truene. `procesa_ceniza.sh` no se entera, escribe la línea del CSV y no deja GeoTIFF.
- Si CSPP falla, solo queda un mensaje en `procesa.log`, que nadie lee.
- Nada avisa si la cadena se detiene (por ejemplo, si cirrus deja de traer L1b o si se desmonta `/data1`).
- El log se llena con avisos sin importancia ("ya hay una corrida en curso", 262 de 288 líneas el 2026-10-19).

**Qué (propuesta).**
1. **Códigos de salida en `lanot-detect-ash`:** 0 = todo bien; 1 = error de procesamiento; 2 = error de uso (el que ya usa argparse); 3 = faltan datos. En rangos: 0 solo si todos los instantes salieron bien.
2. **CSV con estado:** columna `estado` en `latencia_ceniza.csv` (`ok`, `incompleto`, `error_cspp`, `error_ceniza`). Las fallas también quedan registradas, con los tiempos que alcanzó a tener.
3. **Log útil:** la corrida de respaldo (x5:10) no escribe nada si la principal está en curso o ya terminó. Rotación mensual de `procesa.log` (logrotate o el propio script).
4. **Vigilante** `operacion/vigila_ceniza.sh`, cada 15 min por cron:
   - revisa la antigüedad del GeoTIFF más reciente (falla si pasa de 15 min), las fallas de la última hora en el CSV y la latencia (falla si el p95 de la última hora pasa de 6 min);
   - escribe `/data/ceniza/oper/state/estado.json` (estado, último producto, latencia, fallas recientes) para que lo lea un tablero o el dataservice;
   - registra **solo los cambios de estado** (ok → falla y falla → ok) en un log de eventos corto, que es el que se revisa.

**Canal de aviso: solo logs (verificado el 2026-10-19).**
- En tahan, el crontab de lanotadm tiene `MAILTO=""`, no hay `mail`/`sendmail` y postfix está inactivo. La cadena polar tampoco avisa: deja logs en `/var/log/lanot/polares/cadena/` y marcadores de estado en `/data/output/jpss/state/` (con reintentos en `.../reintentos`).
- En cirrus, cron sí manda correo, pero a un buzón local que nadie lee (`/var/spool/mail/lanotadm`, 38 764 mensajes y 340 MB, casi todos salidas de `trae_glm.sh` y `trae_abi.sh`). `archivamail.sh` lo archiva cada mes.

Se sigue la convención de la cadena polar: el log de corridas va en `/var/log/lanot/ceniza/` y el estado en `/data/ceniza/oper/state/` (`estado.json`, eventos). Un aviso activo (correo o mensajería) se puede agregar después leyendo los eventos, sin cambiar lo demás.

**Resultado.** Probado con fallas simuladas (L1b incompletas, `aitf` y `lanot-detect-ash` que fallan a propósito) y con `tests/test_salida.py`. El código 3 de `lanot-detect-ash` (faltan productos L2) se registra como `error_cspp`. En tahan desde el 2026-10-20: el vigilante dio una falsa alarma al instalar (los escaneos de la hora anterior estaban en la carpeta vieja `conus/`); se corrigió para que busque los escaneos procesados en el CSV y no en la carpeta de salida (`b43e6a8`). Desde entonces, estado `ok`.

### P5. Limpieza y documentación

**Qué.**
- `requirements.txt`: quitar Pillow, aggdraw y pyshp (eran de `mapdrawer.py`, que pasó a LANOT_tools). Que coincida con `pyproject.toml`, o eliminarlo y dejar solo `pyproject.toml`. `matplotlib` solo lo usa `compare_ash.py`: dejarlo como opcional (`[project.optional-dependencies]`).
- README: quitar `--png` y la descripción de mapdrawer (se eliminaron en mayo, `b748bda`) y mencionar LANOT_tools para las imágenes.
- `detect_ash.py`: imports al principio, `logger` en lugar de `print` (salvo el resumen final), quitar `Topos` y la doble importación de `Affine`, `sys.exit` en lugar de `exit`, y reescribir `get_moment()` en 3 líneas (hoy es confuso y no lo usa la operación).
- Carpeta `doc/` para decisiones del proyecto:
  - `doc/README.md`: índice.
  - `doc/2026-05-01_refactorizacion.md` (hecho el 2026-10-19): `plan_refactor.md` con fechas y lo que realmente se hizo. Commits del 2026-05-01: `16fd9d2` (GeoTIFF de 1 banda con colormap, moment → instant), `785d9d5` (paleta única y NoData 255), `b748bda` (sin subpaquete ni mapdrawer), `dd91ca1` (`classify_ash`, Loader de Skyfield, `logger.exception`). Después, `9dd4752` (2026-05-04, igualar terascan: R1.37 en la ceniza confirmada de día, HAP con ΔT2 < −1.5 → 0, crepúsculo con límites estrictos).
  - `doc/2026-10-18_operacion_tahan.md`: por qué una cadena aparte en tahan (CSPP mínimo, 4 segmentos, latencia medida).
  - Este plan.

---

## Fase 2: cambios pequeños en la clasificación

### P6. Corregir el ángulo cenital solar

**Por qué.** `get_sun_zenith_angle` combina la RA/Dec astrométrica en J2000 (`astrometric.radec()`) con el tiempo sidéreo aparente **de la fecha** (`gast`). Les falta la precesión desde 2000 (~50″/año). Medido contra el cálculo topocéntrico completo de Skyfield: error de −0.2° (2019), +0.28° (oct. 2026) y −0.35° (jun. 2026). Crece con los años.

**Qué.** `earth.at(t).observe(sun).apparent().radec(epoch='date')`, con lo que el error medido baja a 0.0025°. El resto de la fórmula vectorizada queda igual.

**Efecto.** Solo cambian de bloque los píxeles con SZA a menos de ~0.35° de 70° u 85°, una franja de ~30–40 km que se mueve con el terminador. Se mide con P0 en días con amanecer y atardecer sobre la región.

**¿Fue correcto usar Skyfield? Sí.** La decisión de 2025 (posición del Sol una vez por imagen con efemérides JPL y trigonometría esférica vectorizada para todos los píxeles) es la que bajó el tiempo de ~30 min a segundos, y sigue siendo correcta. El error era de uso (marco J2000 combinado con el tiempo sidéreo de la fecha), no de la biblioteca. Para umbrales de 70° y 85° bastaría una fórmula analítica (NOAA, ~0.01°) sin el archivo `de421.bsp` (17 MB); no vale la pena cambiar mientras Skyfield funcione. pvlib, la alternativa descartada, calcula por punto y sería lenta con millones de píxeles. Con la corrección, la precisión es ~0.003° (~9″), no "sub-arcsecond" como dice el artículo, pero sobra para el uso.

**Resultado.** Error medido contra el cálculo topocéntrico completo: ~0.003° (`tests/test_sza.py`, tolerancia 0.01°). En las 63 escenas cambian 291 píxeles en 13 escenas de amanecer o atardecer (288 sin ceniza → HAP, 2 → LAP, 1 nube → HAP); la CA no cambia.

### P7. Valor de "sin ceniza": 0 en lugar de 255

**Por qué.** Desde mayo (`785d9d5`) el 0 se convierte en 255 al guardar, y "no hay ceniza" queda igual que "no hay datos" (fuera del disco, banda faltante, ACTP sin valor). Para la operación sí importa: un píxel sin datos no es un píxel sin ceniza (por ejemplo, para decir "sin ceniza sobre el volcán" o para una estadística de cobertura).

**Qué (confirmado el 2026-10-19).**
- Guardar 0 = sin ceniza, 1–3 = clases y 255 = sin datos (NoData).
- La transparencia del 0 se resuelve con un estilo `.qml` (ver la prueba en QGIS más abajo): la paleta de un TIFF no guarda alfa.

**Valores reservados.** Las versiones viejas (TeraScan y el prototipo de referencia; ver `ash.cpt`) usaban dos categorías más, que se desecharon:
- 4 = `cloud` (verde): HAP sobre nube de agua líquida. Hoy esos píxeles pasan a LAP (3).
- 5 = `noise` (azul): LAP sobre nube de agua líquida. Hoy pasan a 0.

Quedan **reservadas**: el código no las produce, pero conservan su entrada en la tabla de colores y en la documentación, por si vuelven.

**6 = nube (ceniza no detectable), decidido el 2026-10-19.** Para distinguir "despejado, sin ceniza" de "no se puede saber porque hay nube", que hoy son el mismo 0. Píxeles que quedan en 0 y cuya fase ACTP es de hielo (4) o mixta (3). La fase superenfriada (2) **no** entra por ahora; se revisa con el autor principal (reunión pospuesta al viernes 2026-10-23), junto con P10 y P11. Las nubes de agua líquida no entran, porque son bajas y la ceniza por encima se sigue viendo. Color: gris (160, 160, 160), opaco o semitransparente según las vistas. Es una etiqueta informativa, no cambia ninguna clase de ceniza, y se puede agregar en un commit aparte después del cambio 0/255.

| valor | significado | estado |
|---|---|---|
| 0 | sin ceniza | en uso (de mayo a octubre de 2026 se guardaba como 255) |
| 1 | ceniza confirmada (CA) | en uso |
| 2 | probabilidad alta (HAP) | en uso |
| 3 | probabilidad baja (LAP) | en uso |
| 4 | `cloud`: HAP sobre agua líquida | reservado (versiones viejas) |
| 5 | `noise`: LAP sobre agua líquida | reservado (versiones viejas) |
| 6 | nube: ceniza no detectable (fase mixta o hielo) | en uso desde `e8dc297` |
| 255 | sin datos | en uso |

**Antes de cambiar:** el 255 se introdujo en mayo "para mejorar la compatibilidad con QGIS" (`785d9d5`): así QGIS deja transparente lo que no es ceniza sin configurar nada.

**Prueba en QGIS 3.44 LTR (2026-10-19)**, con GeoTIFF sintéticos de valores 0, 1, 2, 3, 6 y 255, cargados con PyQGIS como al abrir el archivo:

| formato | 0 sin ceniza | 6 nube | 255 sin datos | leyenda |
|---|---|---|---|---|
| actual (0 guardado como 255) | transparente | (no existe) | transparente | 256 clases |
| 0 con alfa 0 en la tabla de colores | **negro opaco** | gris | transparente | 256 clases |
| 0 fuera de una máscara interna (`GDAL_TIFF_INTERNAL_MASK`) | transparente | gris | transparente | 256 clases |
| tabla de colores + estilo `.qml` con el mismo nombre | transparente | gris | transparente | **5 clases con nombre** |

- La paleta de un TIFF solo admite RGB: GDAL descarta el alfa al escribir (se lee de vuelta como 255). El 255 sale transparente solo por ser NoData. Por eso el alfa en la tabla no basta.
- La máscara interna funciona en QGIS, pero los programas que respetan máscaras (por ejemplo, `rasterio.read(masked=True)`) tratarían el 0 como dato faltante, que es justo la confusión que se quiere quitar.
- El estilo `.qml` junto al archivo (`ceniza_X.tif` + `ceniza_X.qml`) lo carga QGIS solo al abrirlo, deja el 0 transparente y además arregla la leyenda: hoy QGIS muestra 256 clases porque la paleta de un TIFF siempre tiene 256 entradas.

**Decisión (2026-10-19, probada también en la interfaz de QGIS):** datos limpios (0, 1–3, 6, 255; NoData = 255; sin máscara), un `ceniza.qml` en el repo y el `.qml` junto a cada GeoTIFF (opción `--sin-qml` para no escribirlo). Costo en operación: ~0.04 ms y ~700 bytes por escaneo. Las vistas web (LANOT_tools) colorean por su cuenta y no dependen de esto.

**Resultado.** En los casos de regresión la ceniza no cambia: 64 536 píxeles pasan de 255 a 0, 547 siguen como sin datos (sin fase o sin alguna banda válida) y 319 pasan de 0 a 6 (nube).

Además hay que revisar quién consume los GeoTIFF (vistas de LANOT_tools, kawak, dataservice) y si alguno depende del 255. Hoy la operación es nueva y solo guarda en tahan, así que es buen momento.

### P8. Límites del crepúsculo

**Por qué.** `(sza > 70) & (sza < 85)` deja sin bloque (clasificación 0) los píxeles con SZA exactamente 70 u 85. Es poco frecuente, pero es un hueco.

**Qué.** Noche: SZA > 85; crepúsculo: 70 ≤ SZA ≤ 85; día: SZA < 70. Es lo que hacía la versión de diciembre.

**Resultado.** 0 píxeles distintos en las 63 escenas: el hueco existía, pero casi nunca se presenta.

### P9. Banda C14

**Por qué.** C14 (11.2 µm) se lee pero no entra en la clasificación; solo en la máscara de datos válidos. Si falta, se pierde el escaneo completo, y cada lectura cuesta E/S.

**Qué.** Dejar de leerla. La máscara de datos válidos usa solo las bandas que sí se usan.

**Resultado.** 0 píxeles distintos en las 63 escenas; los recortes de prueba ya no incluyen C14 y la regresión pasa.

---

## Fase 3: requieren decisión (base del algoritmo)

Aquí no se propone cambiar el código sin antes acordar la regla con el autor principal. Lo que sí se propone es dejarla **explícita**: una tabla en `doc/` y una prueba unitaria por cada caso.

**Dos decisiones separadas (2026-10-21).** El artículo se envió hace un año y describe la versión de diciembre (`90ad79f`): no se le agrega nada que dependa del código mejorado (ni la clase 6, ni la corrección del SZA, ni el kernel nuevo). Por eso:
- **Artículo:** solo se puede ajustar donde el texto no coincide con la versión de diciembre (tabla de abajo), si el autor principal quiere hacerlo en esta revisión.
- **Operación:** P10, P11 y la fase superenfriada en la clase 6 se deciden para el código actual, con los conteos de abajo. La clase 6 es solo de la operación.

**Diferencias entre el texto del artículo y la versión de diciembre** (verificado en `90ad79f`):

| regla | texto | diciembre | hoy | efecto medido |
|---|---|---|---|---|
| CA de día | exige R1.37 > 0.002 | no lo exige | lo exige (mayo) | 3 de 31 737 píxeles de CA (63 escenas, CONUS) |
| HAP con ΔT2 < −1.5 | pasa a 0 | sigue HAP (LAP sobre agua) | pasa a 0 (mayo) | HAP −41 %, LAP −89 % (CONUS) |
| regla de fase (P10) | HAP y LAP con hielo, mixta o superenfriada → 0 | ver tabla de P10 | igual que diciembre | 7 HAP y 2 LAP en la región del artículo |
| ΔT3 sobre la CA (P11) | la CA no cambia | la CA por kernel con ΔT3 ≤ 0 → 0 | igual que diciembre | 857 píxeles de CA en la región |
| crepúsculo | 70° < SZA < 85° | 70° ≤ SZA ≤ 85° | igual que diciembre | 0 |
| precisión del SZA | "sub-arcsecond" | error de 0.2° a 0.35° (marco J2000 con tiempo sidéreo de la fecha) | ~0.003° (P6) | 291 píxeles en 13 escenas |

Las dos primeras filas ya estaban en el texto antes de mayo: en la metodología de noviembre de 2025 (`fase1/Metodology and results 29_11_2025.docx`) y en el manuscrito del 13 de abril de 2026 (`fase2/JimenezetalAshdetection.docx`). El commit de mayo (`9dd4752`, "Correcciones para igualar terascan") ajustó el código al texto, así que esas dos reglas se quedan en el artículo. Queda por confirmar si los números del artículo se recalcularon después del 4 de mayo: las estadísticas de `fase2` son del 22 al 29 de abril.

P11: el manuscrito de abril coincidía con el código ("pixels classified as CA or HAP were removed if … ΔT3 less than 0"). La versión revisada de octubre dice "applied exclusively to HAP … CA remained unchanged". Preguntar al autor principal por qué cambió.

La versión actual (SZA, kernel, clase 6, 0/255) se documenta en el artículo de JOSS, no en este.

### P10. Regla de fase de nube

Hoy (diciembre y mayo, igual):

| clase tras los filtros | fase ACTP | resultado |
|---|---|---|
| HAP (2) | 1 agua líquida | LAP (3) |
| HAP (2) | 4 hielo | 0 |
| HAP (2) | 2 superenfriada, 3 mixta, 5 desconocida, 0 despejado | **sigue HAP** |
| LAP (3) | 1 agua líquida | 0 |
| LAP (3) | 2, 3, 4, 5 | 0 |
| LAP (3) | 0 despejado | sigue LAP |
| CA (1) | cualquiera | sigue CA |

El texto del artículo dice que HAP **y** LAP con hielo, fase mixta o superenfriada pasan a 0, y que HAP con agua líquida pasa a LAP. No dice nada de LAP con agua líquida ni de la fase desconocida. Las diferencias:
- HAP con fase superenfriada o mixta: el texto la elimina; el código la conserva.
- LAP con agua líquida: el código la elimina; el texto no lo menciona.
- Fase 5 (desconocida): el código elimina LAP pero conserva HAP.

El prototipo de referencia usaba las clases 4 y 5 para HAP y LAP con agua líquida (como TeraScan), en lugar de 3 y 0.

**Decisión pendiente:** cuál es la regla buena. Después: prueba unitaria por caso y comparación con P0.

**Medido (2026-10-21).** Las mismas 63 escenas, con la versión actual (`8dd7d78`), en CONUS completo y en la región del artículo (`ashpaper`). Píxeles HAP y LAP que llegan a la regla de fase (después de los filtros de ΔT2 y ΔT3), por fase:

| caso | código | texto | región del artículo | CONUS |
|---|---|---|---|---|
| HAP, superenfriada (2) | sigue HAP | 0 | 1 (1 escena) | 1 094 |
| HAP, mixta (3) | sigue HAP | 0 | 6 (4 escenas) | 5 092 |
| HAP, desconocida (5) | sigue HAP | no dice | 0 | 546 |
| LAP, agua líquida (1) | 0 | no dice | 2 (1 escena) | 1 979 |
| LAP, desconocida (5) | 0 | no dice | 0 | 196 |
| *referencia:* HAP final | | | 836 | 50 773 |

- En la región del artículo, la diferencia entre el código y el texto es de **7 píxeles de HAP** (0.8 %) en 63 escenas, más 2 de LAP. Fuera de la región (CONUS) es mayor, pero ahí casi todo lo que se clasifica no es ceniza del Popocatépetl.
- Clase 6: si la fase superenfriada contara como nube, 2 894 píxeles de la región pasarían de 0 a 6 (la clase 6 crecería 7 %). No cambia ninguna clase de ceniza.
- Los límites exactos (el texto usa `ΔT3 < 0` y `< 1.5`; el código, `≤`) no importan: 0 píxeles en la región y 8 en CONUS.
- Los resultados del artículo se calcularon con la regla del código (diciembre y ahora es la misma). Cualquiera de las dos opciones es defendible por el efecto; la decisión es cuál describe el artículo.

### P11. Filtro de ΔT3 sobre la ceniza confirmada

**¿Modifica la salida?** Sí, pero solo en un caso. La regla `(clase ≤ 2) & (ΔT3 ≤ 0) → 0` también alcanza a la ceniza confirmada (1). La confirmada por umbrales ya exige ΔT3 > 2, así que no le afecta. La que **sí** se elimina es la **confirmada por el kernel** (`nhood == 1`, que no exige ΔT3) cuando ΔT3 ≤ 0. El texto dice que la confirmada "remained unchanged".

**Decisión pendiente:** si el filtro debe aplicarse solo a HAP (como dice el texto) o también a la ceniza confirmada por el kernel (como hace el código). Con P0 se puede contar cuántos píxeles afecta antes de decidir.

**Medido (2026-10-21)**, en las mismas 63 escenas:

| | región del artículo | CONUS |
|---|---|---|
| CA borrada por `ΔT3 ≤ 0` (toda es CA solo por kernel) | **857** (42 escenas) | 95 642 (62 escenas) |
| *referencia:* CA final | 3 100 | 31 734 |
| *referencia:* CA final solo por kernel | 298 | 19 762 |

- Si se siguiera el texto, la CA de la región crecería 28 % (y se triplicaría en CONUS). Es mucho más que P10.
- **No parece ceniza:** los 857 píxeles son todos de noche; ninguno está a menos de 50 km del volcán y solo 28 tocan la CA que queda. 637 están sobre cielo despejado (fase 0), con ΔT3 de −2.6 a 0 K (mediana −1.15). En las escenas de 2024-02-27 de 08:00 a 13:00 UTC crecen hasta 159 por escena, lejos de la pluma. Es lo que se espera de superficies frías o nubes de noche, donde ΔT3 negativo es común.
- No hay verdad de campo para estos píxeles; la conclusión se basa en la distancia al volcán, la vecindad con la pluma y el valor de ΔT3.
- **Recomendación:** dejar el código como está (el filtro también se aplica a la CA por kernel) y corregir el texto del artículo, que dice "the Confirmed Ash (CA) category remained unchanged". Así el texto describe el algoritmo con el que se calcularon los resultados.

Método: `classify_ash` envuelta en un script que recalcula las etapas intermedias y comprueba en cada escena que el resultado final sea idéntico al de la función (lo fue en las 126 corridas).

---

## Lo que no entra en este plan

- Corregir el artículo. Las diferencias de texto (P10, P11, "sub-arcsecond accuracy" en la sección 2.4, "0 = no ash", los límites del crepúsculo) quedan anotadas por si el autor principal quiere ajustarlas en esta revisión, pero no se las pidieron.
- La fórmula del kernel (ΔT1 − X̄·σ): coincide con el artículo y no se toca.

## Decisiones que necesito

1. ~~Canal de aviso para P4~~: solo logs y estado, como la cadena polar (2026-10-19).
2. ~~P7: 0 = sin ceniza, 255 = sin datos~~: confirmado (2026-10-19), con 4 y 5 reservados y 6 = nube (fases mixta y hielo).
3. Con el autor principal (reunión pospuesta al viernes 2026-10-23): P10, P11 y si la fase superenfriada cuenta como nube (6).
4. ~~P1: `--jobs`~~: se elimina junto con el kernel vectorizado (2026-10-19).

## Seguimiento

| punto | commit | nota |
|---|---|---|
| P0 | `6a366a5` | 3 casos reales (noche, crepúsculo, día) + pruebas por regla |
| P1 | `6e3629d` | idéntico en 63 escenas CONUS completas (2024-02-27 y 2019-03-01): 0 píxeles distintos; 2.6 s por escena contra ~45 s antes (6 núcleos) |
| P2 | `aa57f3c` | mismos 63/63 instantes completos en la muestra de 2019 y 2024 |
| P3 | `8ee5257` | `tests/test_rutas.py` |
| P4 | `3073b65` | códigos de salida: 0 bien, 1 error, 2 uso, 3 faltan datos |
| P5 | `8196b08` | README, `compare_ash.py`, sin `requirements.txt`; matplotlib opcional; este documento y `2026-10-18_operacion_tahan.md` |
| P7 (0 y `.qml`) | `6959b70` | sin ceniza = 0, sin datos = 255, `.qml` junto a cada GeoTIFF; probado en QGIS 3.44 LTR |
| P7 (6 = nube) | `e8dc297` | fases mixta y hielo; 319 píxeles de 65 352 en los casos de regresión |
| P6 | `a888c98` | 63 escenas: 291 píxeles cambian en 13 escenas de amanecer o atardecer (288 sin ceniza → HAP, 2 → LAP, 1 nube → HAP); la CA no cambia |
| P8 | `fd20e2e` | 63 escenas: 0 píxeles distintos (el SZA exacto en 70 u 85 casi no ocurre) |
| P9 | `25861d7` | 63 escenas: 0 píxeles distintos |
| `vigila_ceniza.sh` | `b43e6a8` | escaneos perdidos según el CSV y no la carpeta de salida (falsa alarma al cambiar RECORTE) |

## Comparación con la versión del artículo (2026-10-20)

Versión de diciembre de 2025 (`90ad79f`, con la que se hicieron los resultados del artículo) contra la final de la fase 2 (`25861d7`), en las mismas 63 escenas CONUS completas (2024-02-27 y 2019-03-01), solo clases de ceniza (`compara_salidas.py --solo-ceniza`):

| diciembre \ final | sin ceniza | CA | HAP | LAP |
|---|---|---|---|---|
| sin ceniza | 236 103 535 | 0 | 289 | 2 |
| CA | 3 | 31 734 | 0 | 0 |
| HAP | 35 450 | 0 | 50 484 | 0 |
| LAP | 25 464 | 0 | 0 | 3 039 |

- **Ceniza confirmada: igual** (3 de 31 737 píxeles; la CA diurna exige R1.37 > 0.002 desde mayo).
- **HAP −41 % y LAP −89 %, por un solo cambio de mayo** (`9dd4752`): el HAP con ΔT2 < −1.5 pasa a 0, como dice el texto del artículo. En diciembre esos píxeles seguían como HAP, o bajaban a LAP si la fase era agua líquida, porque la regla de fase se aplicaba después. Verificado píxel por píxel en 2024-02-27 04:06: todo lo que desaparece tiene ΔT2 < −1.5.
- P6, P8 y P9 suman +291 píxeles (ver arriba).

Para el artículo: los números se calcularon con un algoritmo que conserva el HAP con ΔT2 < −1.5 (y lo convierte en LAP sobre agua líquida), mientras que el texto describe que se elimina. La ceniza confirmada, que domina la detección de eventos, no cambia.
