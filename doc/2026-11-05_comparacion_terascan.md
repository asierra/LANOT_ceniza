# Comparación con la versión de TeraScan

- **Fecha:** 2026-11-05
- **Estado:** día de prueba (2026-11-02) hecho y explicado; falta elegir la muestra y evaluar contra CENAPRED.

## Por qué

El producto que se usa hoy es el de TeraScan, no el de este repositorio. Para pasar a producción hay que saber en qué difieren las dos salidas y cuál detecta mejor.

## La versión de TeraScan

En terascan (`teradm@132.247.103.142`) la cadena es:

1. `configproc/grb.abi.ash.new2`: función `ash_new_m8_altura` sobre las L1b de TeraScan y su máscara de nubes; escribe en `products/tdf/whole_pass/abi/conus/ash3`.
2. `configproc/grb.abi.ash.new.recote.centromex`: remapeo a la región `cenizas_1km` (vecino más cercano).
3. `configproc/grb.abi.ash.new.recote.centromex.geotiff`: exportación a `products/exportadas/geotiff/cenizas2/centromex/`.

El script `/opt/terascan/pass/postprocs/ash_new_m8_altura` es idéntico a `~teradm/backups/pass/postprocs/ash_new_m8_altura`, del **2024-08-10**. Se copió a `/opt/terascan` el 2025-04-07, con el cambio a GOES-19, y no ha cambiado desde entonces. Es anterior a la versión del artículo. Hay copia del script y de las tres configuraciones en `/data/ceniza/terascan/`.

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
- La clase es el valor (1 CA, 2 HAP, 3 LAP, 4 HAP bajo nube). Lo demás es −3.4·10³⁸, así que no se distingue "sin ceniza" de "sin datos".
- Nombre: `AAAA.MMDD.HHMMSS.goes-19.centromex.tif` (inicio del escaneo).

### Archivo

`ls -f` del directorio (2026-11-05): 140 728 GeoTIFF de ceniza, del 2025-04-07 al día de hoy. Los 123 del 2025-04-07 son de GOES-16; el resto, de GOES-19. Hay de 6 500 a 8 000 por mes, de unos 8 900 posibles. La lista está en `/data/ceniza/terascan/terascan_lista.txt`.

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

Archivos: GeoTIFF de TeraScan en `/data/ceniza/terascan/centromex/`; salidas nuestras en `/data/ceniza/terascan/piloto_20261102/`; corridas en `tahan:~/comparacion_terascan/`.

## Pendiente

1. ~~Comprobar que la diferencia del LAP viene de la máscara de nubes~~ (hecho el 2026-11-05: la máscara explica la diferencia con las reglas de TeraScan en Python; la diferencia con `classify_ash` es la regla de fase).
2. ~~Ver qué fase de ACTP tienen los píxeles que TeraScan marca y nosotros no~~ (hecho: la mitad en despejado, por el LAP; la otra mitad bajo nube, por la tabla de fase).
3. Elegir la muestra:
   - días con emisiones según CENAPRED y días tranquilos, de 2025–2026;
   - que cubran día, crepúsculo y noche;
   - con L2 en tahan (en 2026 faltan los días 071, 190 a 216 y 227 a 243).
4. Evaluar contra CENAPRED a nivel de escaneo y de evento.
5. Preguntar a Víctor:
   - si R04 en porcentaje es lo que se pretendía;
   - si en la evaluación la nube (6) cuenta como "no se sabe" o como "sin ceniza";
   - por qué el LAP dejó de ser una prueba propia (ΔT1 < 3 en TeraScan) y pasó a salir del HAP;
   - si la versión de TeraScan debe seguir como referencia.
