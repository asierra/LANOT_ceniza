# Comparación con la versión de TeraScan

- **Fecha:** 2026-11-05
- **Estado:** día de prueba (2026-11-02) hecho y explicado; muestra de 16 días elegida con los avisos del VAAC y en proceso (2026-11-05); falta evaluar y confirmar con CENAPRED.

## Por qué

El producto que se usa hoy es el de TeraScan, no el de este repositorio. Para pasar a producción hay que saber en qué difieren las dos salidas y cuál detecta mejor.

## La versión de TeraScan

En terascan (`teradm@132.247.103.142`) la cadena es:

1. `configproc/grb.abi.ash.new2`: función `ash_new_m8_altura` sobre las L1b de TeraScan y su máscara de nubes; escribe en `products/tdf/whole_pass/abi/conus/ash3`.
2. `configproc/grb.abi.ash.new.recote.centromex`: remapeo a la región `cenizas_1km` (vecino más cercano).
3. `configproc/grb.abi.ash.new.recote.centromex.geotiff`: exportación a `products/exportadas/geotiff/cenizas2/centromex/`.

El script `/opt/terascan/pass/postprocs/ash_new_m8_altura` es idéntico a `~teradm/backups/pass/postprocs/ash_new_m8_altura`, del **2024-08-10**. Se copió a `/opt/terascan` el 2025-04-07, con el cambio a GOES-19, y no ha cambiado desde entonces. Es anterior a la versión del artículo. Hay copia del script y de las tres configuraciones en `tahan:/data/ceniza/comparacion_terascan/terascan/`.

### Reglas

Son expresiones de `emathp`. Con ΔT1 = BT13 − BT15, ΔT2 = BT11 − BT13 y ΔT3 = BT07 − BT13:

| | noche (SZA > 85) | crepúsculo (70 < SZA < 85) | día (SZA < 70) |
|---|---|---|---|
| CA: ΔT1 < 0, ΔT2 > 0, ΔT3 > 2 | sí | con R04 > 0.3 | con R04 > 0.3 |
| HAP: ΔT1 < 1, ΔT2 > −0.5, ΔT3 > 2 | sí | con R04 > 0.3 y BT14 < 273 | con R04 > 0.3 |
| LAP: ΔT1 < 3, ΔT2 > −1, ΔT3 > 2 | con BT14 < 273 | con R04 > 0.3 y BT14 < 273 | con R04 > 0.3 y BT14 < 273 |

- Con SZA exactamente 70 u 85 da 0.
- Con la máscara de nubes de TeraScan (`cloud == 1`), el HAP pasa a 4 y el LAP a 0. La CA no cambia.
- R04 está en **porcentaje**: 0.3 % es 0.003 en fracción (comprobado abajo). El nuestro es 0.002.
- No tiene kernel de textura, ni refinamiento del HAP por ΔT2, ni filtro de ΔT3, ni fase de nube (ACTP).
- Calcula también una altura para la CA (`46.792 − 0.1552·BT13`), que no se exporta.
- Se supone que los archivos entran en orden alfabético (cloudmask, C04, C07, C11, C13, C14, C15). Las pruebas del día de prueba lo confirman.

### Salida

- GeoTIFF de una banda, float32, 432 × 719, en lat/lon (datum "Spherical Earth"), de 107.23° a 93.84° O y de 14.94° a 22.72° N.
- La clase es el valor (1 CA, 2 HAP, 3 LAP, 4). El 4 sale de "HAP bajo nube" en el script, pero la paleta (`ash.cpt`) lo llama "cloud" y lo pinta de verde: quien ve el producto lo lee como nube. En la muestra, casi todo el 4 está a cientos de km del volcán, así que en la evaluación **no cuenta como ceniza** (en el día de prueba sí se contó, pero ese día casi no hubo 4). Lo demás es −3.4·10³⁸, así que no se distingue "sin ceniza" de "sin datos".
- Nombre: `AAAA.MMDD.HHMMSS.goes-19.centromex.tif` (inicio del escaneo).

### Archivo

`ls -f` del directorio (2026-11-05): 140 728 GeoTIFF de ceniza, del 2025-04-07 al día de hoy. Los 123 del 2025-04-07 son de GOES-16; el resto, de GOES-19. Hay de 6 500 a 8 000 por mes, de unos 8 900 posibles. La lista está en `tahan:/data/ceniza/comparacion_terascan/terascan/terascan_lista.txt`.

## Cómo se compara

- **Entradas:** los L2 de CSPP Geo en `tahan:/depot/goes-east/l2/abi/conus/2026/JJJ/PRODUCTO/`. En 2026 faltan los días 071, 190 a 216 y 227 a 243. `lanot-detect-ash` necesita los archivos en una sola carpeta, así que se hace una carpeta de enlaces por día.
- **Tres salidas por instante:**
  1. TeraScan;
  2. `lanot-detect-ash --clip centromexgeo`, la instalación de la operación;
  3. `herramientas/reglas_terascan.py`, que sobre los mismos L2 aplica las reglas de TeraScan (con BCM de CSPP como máscara de nubes) y `classify_ash`. Escribe las dos clasificaciones en la rejilla de TeraScan.
- **Qué compara cada par:**
  - TeraScan contra las reglas de TeraScan en Python mide el efecto de las **entradas**: calibración, remapeo y máscara de nubes de TeraScan contra CSPP.
  - Las reglas de TeraScan contra `classify_ash` mide el efecto del **algoritmo**, con los mismos datos y la misma rejilla.
- **Herramientas:**
  - `herramientas/compara_salidas.py` compara carpetas y ya lee el formato de TeraScan;
  - `herramientas/compara_terascan.py` dibuja el mapa de diferencias de un instante. Antes era `compare_ash.py` (`lanot-compare-ash`); se movió a `herramientas/` el 2026-11-05 y ya no se instala.
- **Calidad:** TeraScan no es la verdad. La referencia independiente son los reportes de CENAPRED.

## Día de prueba: 2026-11-02 (día 306)

Hubo emisiones: casi toda la ceniza está a menos de 100 km del volcán. TeraScan tiene 253 de los 288 escaneos.

**Unidades de R04.** Se corrieron las reglas de TeraScan con R04 > 0.3 y con R04 > 0.003. Con 0.003 coinciden 30 de los 31 píxeles de CA de TeraScan; con 0.3, uno. Por eso R04 está en porcentaje.

**Alineación.** Se movió la ceniza de un lado sobre la del otro. En latitud, el mejor corrimiento es 0 (el datum esférico no afecta). En longitud, nuestra ceniza queda **una columna** (~2 km) al este. La causa probable es la convención de centro o esquina del píxel. Por eso, al comparar píxel por píxel conviene dar 1 píxel de tolerancia.

**Control.** La salida de la operación contra `classify_ash` en `reglas_terascan.py` casi coincide en la ceniza. Lo que difiere viene del doble remuestreo: de la proyección GOES a la rejilla de 0.02° y luego a la de TeraScan.

**Escaneos con ceniza** (253 instantes comunes):

| salida | escaneos con ceniza | a < 100 km | píxeles de ceniza |
|---|---|---|---|
| TeraScan | 169 | 168 | 861 |
| reglas de TeraScan en Python (R04 > 0.003) | 149 | 149 | 424 |
| `classify_ash` sobre los mismos datos | 154 | 150 | 401 |
| operación (`lanot-detect-ash`) | 154 | 150 | 419 |

- Sin tolerancia, con las mismas reglas, TeraScan marca el doble de píxeles que con los L2 de CSPP. La sección siguiente muestra que eso viene de la ubicación del píxel y de la máscara de nubes, no de la calibración.
- **Algoritmo, con los mismos datos:**
  - la CA coincide (49 de 49);
  - del HAP de TeraScan, 197 siguen HAP y 75 pasan a LAP en el nuestro (refinamiento por ΔT2);
  - el LAP de TeraScan queda en 0 o nube en el nuestro (114 píxeles), porque el nuestro solo saca LAP del HAP;
  - el 4 de TeraScan (HAP bajo nube) queda como CA, HAP o LAP en 67 píxeles y como nube en 87;
  - el nuestro agrega 56 píxeles que TeraScan no marca (kernel de textura).
- **Escaneos que ve uno solo:**
  - 33 los ve solo TeraScan, con 1 a 10 píxeles cada uno;
  - 18 los ve solo el nuestro, con 1 a 3 píxeles;
  - de 03 a 06 UTC (noche) TeraScan ve ceniza en los 43 escaneos y el nuestro en 22;
  - a las 13 UTC (amanecer) el nuestro ve ceniza en 9 de 10 escaneos y TeraScan en ninguno;
  - de 19 a 23 UTC el nuestro ve ceniza en 12 de 52 escaneos y TeraScan en 6.

### Qué explica las diferencias

Ceniza = clases 1 a 4. "±1 px": cuenta como coincidencia si hay ceniza del otro lado en el píxel o en uno vecino (ventana de 3 × 3), por el corrimiento de una columna.

| salida comparada con TeraScan | ceniza de TeraScan cubierta, exacta / ±1 px | ceniza propia cerca de la de TeraScan, ±1 px |
|---|---|---|
| reglas de TeraScan, máscara BCM | 47 % / 89 % | 99 % |
| reglas de TeraScan, solo "nublado" (ACM = 3) | 55 % / **96 %** | **99 %** |
| reglas de TeraScan, sin máscara | 57 % / 97 % | 76 % |
| `classify_ash` | 26 % / **62 %** | 90 % |

- **Las entradas casi no pesan.** Con 1 píxel de tolerancia y la máscara "solo nublado" de CSPP, las reglas de TeraScan sobre nuestros L2 reproducen la ceniza de TeraScan: cubren el 96 % y casi no agregan. La máscara de TeraScan se parece a "solo nublado": su clase 4 (HAP bajo nube) aparece en 4 píxeles en todo el día. Sin máscara sobran píxeles, así que alguna máscara sí aplica.
- **La diferencia de fondo es el algoritmo.** `classify_ash` cubre el 62 % de la ceniza de TeraScan; lo que marca está, en un 90 %, junto a ceniza de TeraScan. De los 328 píxeles de TeraScan que no vemos (±1 px):
  - 281 (86 %) están junto a píxeles que marcamos como nube (6);
  - 296 (90 %) los ven las reglas de TeraScan sobre los mismos datos;
  - por clase de TeraScan: 213 LAP, 111 HAP y 4 HAP bajo nube.

  Que estén junto a nube solo dice que la pluma está rodeada de nube. La fase ACTP del propio píxel (escrita en la rejilla de TeraScan) reparte lo que nos falta en dos causas casi iguales:

  | fase ACTP | píxeles que nos faltan | de ellos, LAP de TeraScan | HAP de TeraScan |
  |---|---|---|---|
  | despejado | 171 (52 %) | 126 | 45 |
  | hielo | 87 | 32 | 55 |
  | agua | 52 | 38 | 14 |
  | mixta | 12 | 11 | 1 |
  | superenfriada | 6 | 6 | 0 |

  - **Fase de nube (48 %):** la tabla del perfil quita el HAP bajo hielo y el LAP bajo agua, superenfriada, mixta o hielo. TeraScan dice "hay ceniza"; la nuestra dice sin ceniza o "no se puede saber" (6).
  - **Reglas, en despejado (52 %):** casi todo es LAP. El LAP de TeraScan es una prueba propia con ΔT1 < 3 y ΔT2 > −1. El nuestro solo sale del HAP (ΔT1 < 1) cuando −1.5 ≤ ΔT2 < −1, así que la franja 1 ≤ ΔT1 < 3 no da LAP nunca. El HAP en despejado que nos falta (45) no lo explican las reglas: con fase despejado, nuestro HAP usa los mismos umbrales (el R04 nuestro es incluso más permisivo). Puede venir de la ubicación de la fase (vecino más cercano en la rejilla de TeraScan) o de los datos; falta verificarlo con los valores de cada píxel.
- Las dos son diferencias de criterio, no errores. Cuál acierta más se decide con CENAPRED.

Archivos: GeoTIFF de TeraScan en `tahan:/data/ceniza/comparacion_terascan/terascan/centromex/`; salidas nuestras en `tahan:/data/ceniza/comparacion_terascan/piloto_20261102/`.

## Muestra (2026-11-05)

### Datos disponibles

- **L2 con ACTP en tahan:** 133 días de 2026 con al menos 200 escaneos: del 1 al 9, del 14 al 19 y del 23 al 29 de enero, del 1 de febrero al 10 de marzo, del 17 al 24 de marzo, y del 1 de septiembre al 4 de noviembre. Los demás días tienen CMIP pero no ACTP. La cadena de ceniza (`procesa_ceniza.sh`) genera ACTP, pero lo borra a la hora.
- **L1b CONUS en tahan:** 262 días completos de 2026 (`/depot/goes-east/l1b/abi/conus/2026/`). Con ellos se podría generar ACTP con CSPP (~66 s por escaneo). Para fechas anteriores a octubre de 2026 habría que bajar GFS y OISST de los archivos de NOAA: el caché de tahan solo tiene octubre y noviembre.
- Con L2 y TeraScan (≥ 200 escaneos de cada uno) quedan 114 días.

### Avisos del VAAC de Washington

`herramientas/avisos_vaac.py` bajó los 947 avisos del Popocatépetl de 2025 y 2026 a `tahan:/data/ceniza/comparacion_terascan/vaac/` y los resume en `avisos_popocatepetl.csv`. Cada aviso trae:
- hora de observación en UTC;
- si el satélite vio la ceniza (`OBS VA CLD` con área), si solo se estimó (`EST VA CLD`: la vio una cámara pero el satélite no, casi siempre por nubes) o si no se identificó;
- fuentes: GOES, cámara, modelos, VOLCAT.

Los analistas usan las mismas imágenes de GOES, así que no es una referencia independiente del todo.

`tahan:/data/ceniza/comparacion_terascan/vaac/dias_2026.csv` resume cada día de 2026: escaneos con L2 y de TeraScan, número de avisos, horas de ceniza observada y estimada. Con L2 y TeraScan hay:
- 46 días con ceniza vista por el satélite;
- 2 con ceniza solo estimada;
- 37 sin avisos ese día ni el anterior ni el siguiente.

Los días con ceniza estimada casi todos son de mayo a agosto (temporada de lluvias), cuando no hay ACTP.

**El 2026-11-02 no tiene avisos** (ni el 1 ni el 3), y aun así TeraScan y la nuestra ven ceniza junto al volcán en unos 150 escaneos. Hay dos explicaciones posibles: el VAAC no avisa de emisiones pequeñas, o las dos versiones tienen falsas alarmas fijas en el cráter. Por eso "sin avisos" no quiere decir "sin ceniza". Para los días sin ceniza hace falta CENAPRED.

### Días elegidos

16 días; la lista está en `tahan:/data/ceniza/comparacion_terascan/muestra/dias.txt`.

| grupo | días |
|---|---|
| ceniza vista por el satélite | 2026-01-29 (noche), 02-11 (noche y día), 02-21 (5 avisos), 03-20 (amanecer), 09-01 (noche), 10-28 (4 avisos) |
| con ceniza estimada (nubes) | 2026-01-14, 02-06, 09-16 (solo estimada), 09-23, 10-27, 11-04 |
| sin avisos | 2026-01-17, 02-03, 09-07, 10-05 |

Para cada día, `reglas_terascan.py --r04 0.003 --nube acm3` en tahan (`scripts/corre_dia.sh`; salidas en `tahan:/data/ceniza/comparacion_terascan/muestra/AAAAjjj/`) y los GeoTIFF de TeraScan en `tahan:/data/ceniza/comparacion_terascan/terascan/centromex/`.

### Resultados (2026-11-05)

`herramientas/evalua_muestra.py`: 3 869 escaneos con las tres salidas. Ceniza = clases 1 a 3. "Ve ceniza" = al menos 1 píxel a menos de 100 km del volcán. El detalle por escaneo está en `tahan:/data/ceniza/comparacion_terascan/muestra/escaneos.csv`.

**Avisos del VAAC** (algún escaneo con ceniza a ±15 min de la observación):

| avisos | TeraScan | reglas de TeraScan en Python | nuestra |
|---|---|---|---|
| 29 con ceniza vista por el satélite | 25 | 22 | 21 |
| 7 con ceniza solo estimada (nubes) | 5 | 4 | 4 |

**Escaneos con ceniza cerca del volcán, en los 4 días sin avisos** (949 escaneos):

| TeraScan | reglas de TeraScan en Python | nuestra |
|---|---|---|
| 475 (50 %) | 131 (14 %) | 141 (15 %) |

**Píxeles de ceniza a más de 200 km del volcán, suma de cada día:**

| | TeraScan | reglas de TeraScan en Python | nuestra |
|---|---|---|---|
| mínimo | 22 | 10 | 134 |
| mediana | ~7 000 | ~730 | ~960 |
| máximo | 153 852 (01-14) | 7 623 (01-14) | 7 085 (10-28) |

- **TeraScan ve ceniza cerca del volcán en la mitad de los escaneos, aun en días sin avisos.** Con esa frecuencia, en una ventana de ±15 min (unos 7 escaneos) casi siempre habrá detección, así que sus 25 de 29 aciertos dicen poco. La nuestra marca el 15 % de los escaneos en esos días y acierta 21 de 29.
- No se sabe si la ceniza cerca del volcán en días sin avisos es real: CENAPRED reporta decenas de exhalaciones al día con "ligeras cantidades de ceniza", y el VAAC no avisa de todas. **Para eso hace falta CENAPRED.**
- **Lejos del volcán, TeraScan tiene muchas más falsas alarmas.** Las mismas reglas sobre nuestros datos dan casi siempre bastante menos (de 2 a 270 veces menos según el día), así que vienen sobre todo de las entradas de TeraScan (L1b y máscara de nubes). Contando su clase 4 serían de 76 000 a 357 000 píxeles al día en 12 de los 16 días. La nuestra también tiene falsas alarmas lejos (hasta 7 000 píxeles al día); falta ver qué son.
- La conclusión del día de prueba ("las entradas casi no pesan") vale para ese día, no en general: en septiembre, cerca del volcán, TeraScan ve ceniza en 126 a 213 escaneos por día y sus reglas sobre nuestros datos en 2 a 38.

## Velocidad (2026-11-05)

**TeraScan.** Datos de los registros de cada paso (`/opt/terascan/pass/logfiles/pprocs/`) para los 251 escaneos del 2026-11-04 que llegaron a GeoTIFF (de 288). Segundos desde el inicio del escaneo, mediana:

| paso | empieza | termina | dura |
|---|---|---|---|
| ingesta de las L1b (C04 a C15) | 183 | 194 | 11.5 |
| máscara de nubes de TeraScan | 203 | 217 | 14.7 |
| ceniza (`ash_new_m8_altura`, **CONUS completo**) | 215 | 225 | 9.8 |
| recorte a `centromex` | 227 | 232 | 4.3 |
| exportación a GeoTIFF | 234 | **236** | 2.0 |

**Nuestra operación** (`latencia_ceniza.csv`, los 288 escaneos del mismo día, todos `ok`):

| paso | dura (mediana) |
|---|---|
| llegada a cirrus | 184 s después del inicio del escaneo |
| CSPP (`cmi,acm,actp`, CONUS completo, 4 segmentos) | 64.6 |
| ceniza (`--clip ashpapergeo`) | 1.0 |
| **total** | **259** |

**Solo el paso de ceniza**, medido en tahan con un escaneo (`/usr/bin/time`, 3 corridas):

| | tiempo | memoria |
|---|---|---|
| `--clip ashpapergeo` (operación) | 1.1 s | 400 MB |
| `--clip centromexgeo` (región de TeraScan) | 1.1 s | 400 MB |
| CONUS completo, sin recorte | 2.1 s | 830 MB |

- **De punta a punta, TeraScan es unos 23 s más rápido:** 236 s contra 259 s. Los datos llegan a las dos máquinas a la misma hora (~184 s).
- **La diferencia está antes del algoritmo.** TeraScan ingiere las L1b y hace su máscara de nubes en ~33 s; CSPP tarda ~65 s, porque calcula ACM y la fase de nube (ACTP), que es más elaborada.
- **Nuestro paso de ceniza es más rápido que el de TeraScan.** Recortado tarda 1 s, y en CONUS completo 2 s. TeraScan tarda unos 16 s entre clasificación, recorte y exportación. TeraScan clasifica todo el CONUS y luego recorta; la nuestra recorta antes de clasificar.
- **Escaneos completos ese día:** TeraScan generó GeoTIFF en 251 de 288 escaneos (87 %); la nuestra, en los 288.
- `operacion/README.md` dice que el CONUS completo tarda ~9 s más que el recorte. Hoy medí 1 s más (2.1 contra 1.1 s); falta ver si esa nota es de antes de las mejoras de octubre.

### Acortar CSPP (2026-11-05)

TeraScan no usa ACTP: su script recibe la máscara de nubes de TeraScan, que solo sirve para pasar HAP bajo nube a 4 y LAP bajo nube a 0. La nuestra necesita ACM y ACTP, y por eso CSPP. CSPP no puede procesar solo una región, pero sí repartir el trabajo.

**Dónde se va el tiempo** (escaneo 2026-309 21:41 UTC, etapas corridas a mano, configuración actual de 4 segmentos):

| etapa | tiempo |
|---|---|
| CMIP (16 bandas, de una en una) | 7.8 s |
| preprocesamiento | 6.8 s |
| algoritmos: ACM y ACTP, 4 segmentos en paralelo | 35.8 s |
| posprocesamiento | 12.6 s |
| resto | ~1 s |

**Pruebas:**
- Correr solo los segmentos que cubren México no funciona: el posprocesamiento necesita los metadatos de todos los segmentos (`Cannot resolve XPath 'TOTAL_PIX'`).
- Con **48 segmentos** (`--max-segment-rows 125 --max-segment-cols 625 -j 48`), los algoritmos tardan 17.1 s en vez de 35.8 s.
- Con **CMIP en paralelo** (`--cmip-args "--cmi --environment CG -P 16"`), CMIP tarda 3.0 s en vez de 7.8 s. Los 16 CMI salen idénticos.

**CSPP completo** (dos corridas de cada configuración, cada una con caché temporal vacío):

| configuración | tiempo |
|---|---|
| actual: `--max-segment-rows 375` | 65.3 y 65.7 s |
| nueva: 48 segmentos, `-j 48`, CMIP con `-P 16` | 42.7 y 44.5 s |

**Resultado idéntico:**
- ACM, BCM y los CMI que usamos (C04, C07, C11, C13, C15) no cambian ni un píxel.
- La fase (ACTP) cambia en 4 píxeles de todo el CONUS, ninguno en la región de la operación.
- El GeoTIFF de ceniza `ashpapergeo` es idéntico. En el CONUS completo cambian 4 de 3 750 000 píxeles.

**24 segmentos.** En tahan corre también la cadena polar, así que se usan 24 trabajos y no 48. Tiempos con `-j 24` y CMIP con `-P 16`:

| partición | tiempo |
|---|---|
| 12 × 2 (125 filas × 1250 columnas) | 44.4 y 46.0 s |
| 6 × 4 (250 × 625) | 41.5 y 42.9 s |
| 4 × 4 (375 × 625) | 43.5 s |

**El pronóstico numérico cambia el resultado, no la partición.** La configuración actual, corrida dos veces con dos horas de diferencia, dio máscaras distintas en 61 513 píxeles (755 en la región), porque entre una y otra llegaron al caché un RAP (17:30) y un GFS (17:54) nuevos, y CSPP usa el más reciente. Comparadas con una corrida de la misma hora, las tres particiones dan el mismo ACM y BCM. La fase difiere en 1 a 8 píxeles de todo el CONUS, ninguno en la región. Consecuencia: reprocesar un escaneo horas después puede dar un producto algo distinto al de la operación.

**Aplicado en `operacion/procesa_ceniza.sh`** (6 × 4, `TRABAJOS=24`, `PROCESOS_CMIP=16`; se cambian con variables de entorno). Probado en tahan con `BASE` propio: CSPP tardó 41.9 s y el escaneo quedó `ok`. La latencia debería bajar de ~259 a ~236 s, casi la de TeraScan. Falta reinstalar en tahan (`git pull && operacion/instala.sh`) y medir un día completo. Las corridas de prueba están en `tahan:/data/ceniza/comparacion_terascan/velocidad/cspp/`.

## Pendiente

1. ~~Comprobar que la diferencia del LAP viene de la máscara de nubes~~ (hecho el 2026-11-05: la máscara explica la diferencia con las reglas de TeraScan en Python; la diferencia con `classify_ash` es la regla de fase).
2. ~~Ver qué fase de ACTP tienen los píxeles que TeraScan marca y nosotros no~~ (hecho: la mitad en despejado, por el LAP; la otra mitad bajo nube, por la tabla de fase).
3. ~~Elegir la muestra~~ (hecho con los avisos del VAAC; ver "Muestra").
4. ~~Evaluar la muestra contra los avisos del VAAC~~ (hecho; ver "Resultados"). Mejoras posibles:
   - exigir que la ceniza caiga dentro del área del aviso (los avisos traen el polígono);
   - ver qué son las falsas alarmas lejanas de la nuestra (10-28, 09-01, 09-07).
5. Pedir a CENAPRED los eventos con ceniza confirmada (hora, tipo, cómo se confirmó) y los días sin ceniza de la muestra, sobre todo:
   - el 2026-11-02;
   - los días sin avisos;
   - los eventos bajo nubes.
6. Si hace falta un evento fuera de las fechas con ACTP, generarlo con CSPP desde las L1b (bajando GFS y OISST).
7. ~~Reinstalar en tahan con la configuración nueva de CSPP~~ (instalado `f86df93` el 2026-11-06 a las 00:12 UTC; los primeros escaneos, 00:11 y 00:16, dieron CSPP 42.8 y 43.4 s y total 237 y 238 s). Falta:
   - medir el día completo del 2026-11-06 en `latencia_ceniza.csv`: mediana y p95 de `cspp_s` y `total_s`, y que no haya fallas;
   - comprobar que la cadena polar de tahan no se alentó con los 24 trabajos de CSPP;
   - si todo va bien, borrar las pruebas de `tahan:/data/ceniza/comparacion_terascan/velocidad/cspp/` (1.9 GB).
8. Preguntar a Víctor:
   - si R04 en porcentaje es lo que se pretendía;
   - si en la evaluación la nube (6) cuenta como "no se sabe" o como "sin ceniza";
   - por qué el LAP dejó de ser una prueba propia (ΔT1 < 3 en TeraScan) y pasó a salir del HAP;
   - si la versión de TeraScan debe seguir como referencia.

## Dónde está cada cosa

Los datos de la comparación no están en el repositorio. Están en **tahan:/data/ceniza/comparacion_terascan/** (grupo `ash`), que se ve desde cualquier máquina con acceso a tahan:

| carpeta | contenido |
|---|---|
| `terascan/` | GeoTIFF de TeraScan (`centromex/`, día de prueba y los 16 días); `terascan_lista.txt`, la lista del archivo de TeraScan; `plantilla.tif`, su rejilla; copia del script `ash_new_m8_altura` y de las tres configuraciones |
| `vaac/` | avisos del VAAC (`avisos/`, `avisos_popocatepetl.csv`), `dias_2026.csv`, y disponibilidad de L1b y L2 en tahan |
| `l2/` | una carpeta por día (`2026jjj/`) con enlaces a los L2 de `/depot` (los 8 productos que usa `reglas_terascan.py`) |
| `piloto_20261102/` | día de prueba: salidas de la operación (`nuestra/`), de `reglas_terascan.py` con R04 0.3 y 0.003 y con las tres máscaras, y la fase ACTP en la rejilla de TeraScan (`fase/`) |
| `muestra/` | los 16 días (`2026jjj/terascan_py`, `2026jjj/nuestra`), `dias.txt`, `escaneos.csv` |
| `scripts/` | `corre_dia.sh` (corre la muestra de un día), `fase_en_rejilla.py`, y la copia de `reglas_terascan.py` que se usó |
| `velocidad/` | tiempos de TeraScan y de la operación del 2026-11-04; pruebas de CSPP (`cspp/`) y del paso de ceniza (`detect_ash/`) |

Para correr la muestra de otro día: `scripts/corre_dia.sh JJJ`, con `JJJ` el día juliano de 2026. Para evaluarla, desde cualquier máquina con el repositorio y acceso a esa carpeta: `herramientas/evalua_muestra.py --terascan .../terascan/centromex --muestra .../muestra --avisos .../vaac/avisos_popocatepetl.csv`.
