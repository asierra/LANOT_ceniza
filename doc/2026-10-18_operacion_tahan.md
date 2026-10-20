# Cadena de ceniza de baja latencia en tahan

- **Fecha:** 2026-10-18 (en operación desde ~22:15 UTC). Documento escrito el 2026-10-19.
- **Estado:** implementado. Detalles de instalación y operación en `operacion/README.md`.

## Problema

Un revisor del artículo preguntó por la latencia total, incluido CSPP. En la cadena existente de cirrus, el algoritmo de ceniza depende del producto Cloud Phase (ACTP), que CSPP Geo AIT genera junto con todos los demás productos L2. Medido el 2026-10-17 en 288 escaneos CONUS: **8.6 min** de mediana desde el inicio del escaneo hasta el Cloud Phase (p95 9.0).

Dónde se iba el tiempo (escaneo de 17:21 UTC del 2026-10-18):

| paso | duración |
|---|---|
| escaneo ABI | 2:39 |
| L1b completa en la estación | 0:11 |
| espera al cron de `trae_abi.sh` (*/5) + rsync | 0:56 |
| CSPP: CMIP + preprocesamiento | 1:10 |
| CSPP: algoritmos, 2 segmentos | 3:33 |
| CSPP: posprocesamiento + compresión | 0:27 |
| **total** | **8:58** |

## Pruebas de CSPP (escaneo de 17:21 UTC)

| prueba | segmentos | total aitf | Cloud Phase y máscara vs. operativo |
|---|---|---|---|
| operativo (todos los productos) | 2 | 5.1 min | — |
| `--products cmi,acm,actp` | 2 | 2.0 min | idénticos |
| todos, `--max-segment-rows 375` | 4 | 3.6 min | idénticos (cambian ~0.16 % de los píxeles de altura de nubes) |
| **`cmi,acm,actp` + `--max-segment-rows 375`** | 4 | **1.5 min** | idénticos |

## Decisiones

1. **Una cadena aparte, en tahan, sin tocar la de cirrus.** cirrus sigue generando todos los productos L2. tahan lee las L1b y el caché dinámico de CSPP del `/data` de cirrus (montado como `/data1`) y corre CSPP solo con `cmi,acm,actp` en 4 segmentos, con su propio caché temporal.
2. **Recoger antes las L1b.** En cirrus, `trae_abi.sh conus` pasó de x5:00 a x4:20 (la última banda llega a la estación entre x4:10 y x4:15). En tahan, la ceniza corre a las x4:30, con un respaldo a las x5:10.
3. **Instalación propia** en `/opt/lanot/ceniza` (ambiente de Python del sistema, sin conda ni cuentas personales), desde un clon en `~/src` con `operacion/instala.sh`. No se copian scripts directamente a los servidores.
4. **Producto:** al principio, el GeoTIFF CONUS completo. Desde el 2026-10-19 (`feb5241`), solo el recorte de la región del artículo en lat/lon (`ashpapergeo`), guardado en tahan; dónde se publica queda pendiente.

## Resultado

Día completo del 2026-10-19 UTC (288 de 288 escaneos, sin fallas), del inicio del escaneo al GeoTIFF de ceniza:

| tramo | mediana | p95 |
|---|---|---|
| L1b en cirrus | 184 s | 185 s |
| CSPP (cmi, acm, actp; 4 segmentos) | 65 s | 69 s |
| ceniza (CONUS completo) | 9.2 s | 9.8 s |
| **total** | **4.5 min** | **4.5 min** |

Mismo día en la cadena completa de cirrus, con el cron nuevo: 7.9 min hasta el Cloud Phase (p95 8.4; antes 8.6). En las pruebas del 2026-10-18 (dos escaneos), la ceniza de tahan salió idéntica, píxel por píxel, a la calculada con las L2 completas de cirrus.

Después de esta medición, el kernel vectorizado (`6e3629d`) bajó el cálculo de la desviación estándar local de 7.3 s (16 procesos) a 0.17 s (1 proceso), medido en tahan, y el recorte a la región del artículo reduce aún más el paso de ceniza.
