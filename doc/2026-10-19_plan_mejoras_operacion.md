# Plan de mejoras para la operación de `detect_ash.py`

- **Fecha:** 2026-10-19
- **Estado:** aprobado el 2026-10-19. Fases 0 y 1 implementadas el mismo día (ver "Seguimiento" al final); de la fase 2, P7 en curso; el resto de las fases 2 y 3, pendiente.
- **Rama:** `operacion-tahan`

## Contexto

El código no se revisaba desde mayo de 2026 (refactorización) y la parte científica no ha cambiado desde diciembre de 2025. Ahora corre en operación en tahan cada 5 minutos (`operacion/procesa_ceniza.sh`, desde el 2026-10-18). Este plan busca que la **operación** sea correcta, rápida y vigilable. No busca cambiar el artículo: para la revisión solo se pidió la latencia, que ya se midió.

**Versiones de referencia:**

| nombre | commit | dónde | uso |
|---|---|---|---|
| diciembre | `90ad79f` (2025-12-06; ciencia idéntica a `c93d979`) | `tahan:/opt/LANOT_ceniza.old` | produjo los resultados del artículo |
| mayo | `9dd4752` (2026-05-04) | `tahan:/opt/LANOT_ceniza` | refactorización + "igualar terascan" |
| operación | `feb5241` | `tahan:/opt/lanot/ceniza` (pendiente de instalar) | lo que corre hoy, con la ciencia de mayo |

Datos para comparar: en tahan siguen las entradas L2 del 2024-02-27 (`/data/ceniza/l2/2024/02/27`) y las 168 salidas de diciembre (`/data/ceniza/output/20240227`). Para 2019 y 2023 también hay entradas en `/data/ceniza/l2`.

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
- Script `herramientas/compara_versiones.py`. Corre dos versiones (dos commits, o dos instalaciones) sobre el mismo conjunto de instantes y reporta por clase: píxeles que cambian, matriz de confusión 0/1/2/3/255 y escaneos con ceniza que aparecen o desaparecen. La salida de diciembre es RGBA; se decodifica a clases por color (rojo = 1, naranja = 2, amarillo = 3, transparente = 0 o sin datos).
- Pruebas con `pytest`:
  - **Unitarias** de `classify_ash` con arreglos sintéticos pequeños, un caso por regla (cada umbral, cada bloque de iluminación, cada regla de fase). Documentan la regla y detectan cambios accidentales.
  - **Regresión** con un recorte pequeño de un caso real (por ejemplo, 2019-03-01, el de la animación), con la salida esperada guardada en el repo (unos KB).
- La comparación grande (días completos) se corre a mano en tahan. No va en las pruebas.

**Riesgo.** Ninguno; no toca la operación.

---

## Fase 1: sin cambio en la clasificación

### P1. Kernel estadístico vectorizado

**Por qué.** La desviación estándar local usa `ndimage.generic_filter(np.nanstd)`, que llama a Python por cada píxel. En CONUS tarda 7.3 s con 16 procesos, casi todo el paso de ceniza.

**Qué.** Calcular media y desviación con `uniform_filter` sobre x, x² y el conteo de valores válidos (en float64), con var = E[x²] − E[x]². Se eliminan el `ProcessPoolExecutor`, la opción `--jobs` y la variable `LANOT_CENIZA_JOBS`. Las dos se agregaron el 2026-10-18 (`4132e64`) solo para limitar los procesos del kernel en tahan; únicamente las usa `procesa_ceniza.sh` (no el crontab), que se ajusta en el mismo commit. No hay nada que mantener por compatibilidad.

**Medido (2026-10-19, en tahan, arreglo de 1500×2500 con 5 % de NaN):** 7.30 s con 16 procesos contra 0.17 s con 1 proceso. Diferencia máxima de 2e-7; los NaN coinciden.

**Verificación.** Con P0, en días completos. Se espera clasificación idéntica, salvo píxeles justo en un umbral (diferencia de redondeo); se cuentan.

**Efecto en la operación.** El paso de ceniza baja de ~9 s a ~2 s y se liberan 16 núcleos de tahan para la cadena polar.

### P2. Búsqueda de archivos con expresión regular estricta

**Por qué.** `get_filelist_from_path` acepta un archivo si `'C04' in nombre`, lo que también deja pasar L1b (`RadC-M6C04`), PACUS (`CMIPP`) u otros satélites. Y `process_instant` vuelve a asociar archivos a productos con otra regla distinta. Además, si hay duplicados, el elegido depende del orden del sistema de archivos.

**Qué.** Una sola función con una expresión regular por producto, por ejemplo `^(OR|CG)_ABI-L2-CMIPC-M\dC04_G\d{2}_s(\d{11})`. Se agrega la detección del satélite (G16/G19) y se exige que todos los archivos sean del mismo satélite y dominio (C = CONUS, F = disco completo). Los duplicados se resuelven de forma determinista (CG_ antes que OR_, y luego la fecha de creación `_c` más reciente).

**Verificación.** Pruebas unitarias con listas de nombres reales (M3, M6, G16, G19, CG_, OR_, L1b mezclados) y `--dry-run` sobre los árboles históricos de 2019, 2023 y 2024: mismo número de instantes completos que hoy.

### P3. Rutas configurables

**Por qué.** `/usr/local/share/lanot/skyfield` está fija y además se intenta crear (`mkdir`), lo que falla por permisos fuera de LANOT. El paquete se anuncia como código abierto. `/data/ceniza/l2` también está fija como entrada por omisión.

**Qué.** Variables de entorno `LANOT_SKYFIELD_DIR` (por omisión la ruta actual si existe; si no, el caché de usuario `~/.cache/lanot_ceniza`) y `LANOT_CENIZA_L2`. Sin `mkdir` en rutas del sistema. Un mensaje claro si falta `de421.bsp` (o se descarga en el caché de usuario).

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
   - escribe `/data/ceniza/oper/estado.json` (estado, último producto, latencia, fallas recientes) para que lo lea un tablero o el dataservice;
   - registra **solo los cambios de estado** (ok → falla y falla → ok) en un log de eventos corto, que es el que se revisa.

**Canal de aviso: solo logs (verificado el 2026-10-19).**
- En tahan, el crontab de lanotadm tiene `MAILTO=""`, no hay `mail`/`sendmail` y postfix está inactivo. La cadena polar tampoco avisa: deja logs en `/var/log/lanot/polares/cadena/` y marcadores de estado en `/data/output/jpss/state/` (con reintentos en `.../reintentos`).
- En cirrus, cron sí manda correo, pero a un buzón local que nadie lee (`/var/spool/mail/lanotadm`, 38 764 mensajes y 340 MB, casi todos salidas de `trae_glm.sh` y `trae_abi.sh`). `archivamail.sh` lo archiva cada mes.

Se sigue la convención de la cadena polar: el log de corridas va en `/var/log/lanot/ceniza/` y el estado en `/data/ceniza/oper/state/` (`estado.json`, eventos). Un aviso activo (correo o mensajería) se puede agregar después leyendo los eventos, sin cambiar lo demás.

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

### P7. Valor de "sin ceniza": 0 en lugar de 255

**Por qué.** Desde mayo (`785d9d5`) el 0 se convierte en 255 al guardar, y "no hay ceniza" queda igual que "no hay datos" (fuera del disco, banda faltante, ACTP sin valor). Para la operación sí importa: un píxel sin datos no es un píxel sin ceniza (por ejemplo, para decir "sin ceniza sobre el volcán" o para una estadística de cobertura).

**Qué (confirmado el 2026-10-19).**
- Guardar 0 = sin ceniza, 1–3 = clases y 255 = sin datos (NoData).
- En la tabla de colores, 0 y 255 transparentes (GDAL admite alfa en el colormap), para que la vista sea igual que hoy.

**Valores reservados.** Las versiones viejas (TeraScan y el prototipo de referencia; ver `ash.cpt`) usaban dos categorías más, que se desecharon:
- 4 = `cloud` (verde): HAP sobre nube de agua líquida. Hoy esos píxeles pasan a LAP (3).
- 5 = `noise` (azul): LAP sobre nube de agua líquida. Hoy pasan a 0.

Quedan **reservadas**: el código no las produce, pero conservan su entrada en la tabla de colores y en la documentación, por si vuelven.

**6 = nube (ceniza no detectable), decidido el 2026-10-19.** Para distinguir "despejado, sin ceniza" de "no se puede saber porque hay nube", que hoy son el mismo 0. Píxeles que quedan en 0 y cuya fase ACTP es de hielo (4) o mixta (3). La fase superenfriada (2) **no** entra por ahora; se revisa con el autor principal (~2026-10-21), junto con P10 y P11. Las nubes de agua líquida no entran, porque son bajas y la ceniza por encima se sigue viendo. Color: gris (160, 160, 160), opaco o semitransparente según las vistas. Es una etiqueta informativa, no cambia ninguna clase de ceniza, y se puede agregar en un commit aparte después del cambio 0/255.

| valor | significado | estado |
|---|---|---|
| 0 | sin ceniza | en uso (hoy se guarda como 255) |
| 1 | ceniza confirmada (CA) | en uso |
| 2 | probabilidad alta (HAP) | en uso |
| 3 | probabilidad baja (LAP) | en uso |
| 4 | `cloud`: HAP sobre agua líquida | reservado (versiones viejas) |
| 5 | `noise`: LAP sobre agua líquida | reservado (versiones viejas) |
| 6 | nube: ceniza no detectable (fase mixta o hielo) | decidido; se implementa después del cambio 0/255 |
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

**Propuesta:** datos limpios (0, 1–3, 6, 255; NoData = 255; sin máscara), un `ceniza.qml` en el repo y la opción de escribir el `.qml` junto a cada GeoTIFF (en operación, siempre; es ~1 KB). Las vistas web (LANOT_tools) colorean por su cuenta y no dependen de esto.

Además hay que revisar quién consume los GeoTIFF (vistas de LANOT_tools, kawak, dataservice) y si alguno depende del 255. Hoy la operación es nueva y solo guarda en tahan, así que es buen momento.

### P8. Límites del crepúsculo

**Por qué.** `(sza > 70) & (sza < 85)` deja sin bloque (clasificación 0) los píxeles con SZA exactamente 70 u 85. Es poco frecuente, pero es un hueco.

**Qué.** Noche: SZA > 85; crepúsculo: 70 ≤ SZA ≤ 85; día: SZA < 70. Es lo que hacía la versión de diciembre.

### P9. Banda C14

**Por qué.** C14 (11.2 µm) se lee pero no entra en la clasificación; solo en la máscara de datos válidos. Si falta, se pierde el escaneo completo, y cada lectura cuesta E/S.

**Qué.** Dejar de leerla. La máscara de datos válidos usa solo las bandas que sí se usan.

---

## Fase 3: requieren decisión (base del algoritmo)

Aquí no se propone cambiar el código sin antes acordar la regla con el autor principal. Lo que sí se propone es dejarla **explícita**: una tabla en `doc/` y una prueba unitaria por cada caso.

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

### P11. Filtro de ΔT3 sobre la ceniza confirmada

**¿Modifica la salida?** Sí, pero solo en un caso. La regla `(clase ≤ 2) & (ΔT3 ≤ 0) → 0` también alcanza a la ceniza confirmada (1). La confirmada por umbrales ya exige ΔT3 > 2, así que no le afecta. La que **sí** se elimina es la **confirmada por el kernel** (`nhood == 1`, que no exige ΔT3) cuando ΔT3 ≤ 0. El texto dice que la confirmada "remained unchanged".

**Decisión pendiente:** si el filtro debe aplicarse solo a HAP (como dice el texto) o también a la ceniza confirmada por el kernel (como hace el código). Con P0 se puede contar cuántos píxeles afecta antes de decidir.

---

## Lo que no entra en este plan

- Corregir el artículo. Las diferencias de texto (P10, P11, "sub-arcsecond accuracy" en la sección 2.4, "0 = no ash", los límites del crepúsculo) quedan anotadas por si el autor principal quiere ajustarlas en esta revisión, pero no se las pidieron.
- La fórmula del kernel (ΔT1 − X̄·σ): coincide con el artículo y no se toca.

## Decisiones que necesito

1. ~~Canal de aviso para P4~~: solo logs y estado, como la cadena polar (2026-10-19).
2. ~~P7: 0 = sin ceniza, 255 = sin datos~~: confirmado (2026-10-19), con 4 y 5 reservados y 6 = nube (fases mixta y hielo).
3. Con el autor principal (~2026-10-21): P10, P11 y si la fase superenfriada cuenta como nube (6).
4. ~~P1: `--jobs`~~: se elimina junto con el kernel vectorizado (2026-10-19).

## Seguimiento

| punto | commit | nota |
|---|---|---|
| P0 | `6a366a5` | 3 casos reales (noche, crepúsculo, día) + pruebas por regla |
| P1 | `6e3629d` | idéntico en 63 escenas CONUS completas (2024-02-27 y 2019-03-01): 0 píxeles distintos; 2.6 s por escena contra ~45 s antes (6 núcleos) |
| P2 | `aa57f3c` | mismos 63/63 instantes completos en la muestra de 2019 y 2024 |
| P3 | `8ee5257` | |
| P4 | `3073b65` | códigos de salida: 0 bien, 1 error, 2 uso, 3 faltan datos |
| P5 | `8196b08` | README, `compare_ash.py`, sin `requirements.txt`; matplotlib opcional; este documento y `2026-10-18_operacion_tahan.md` |
| P7 (0 y `.qml`) | `6959b70` | sin ceniza = 0, sin datos = 255, `.qml` junto a cada GeoTIFF; probado en QGIS 3.44 LTR |
| P7 (6 = nube) | (este commit) | fases mixta y hielo; 319 píxeles de 65 352 en los casos de regresión |
