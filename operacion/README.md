# Operación de baja latencia (tahan)

`procesa_ceniza.sh` genera el producto de ceniza CONUS de cada escaneo sin depender de la cadena L2 completa de cirrus:

1. Lee las L1b CONUS que cirrus trae de la estación (`/data1/input/abi/l1b/conus`, que es el `/data` de cirrus montado en tahan).
2. Corre CSPP Geo AIT solo con `cmi,acm,actp` y en 4 segmentos (`--max-segment-rows 375`). Usa el caché dinámico de cirrus (`/data1/aitf_2_3_cache`) y un caché temporal propio (`/data/ceniza/oper/aitf_temporal_cache`).
3. Corre `detect_ash.py` y deja el GeoTIFF en `/data/ceniza/oper/conus/`.
4. Agrega a `/data/ceniza/oper/latencia_ceniza.csv` la llegada de la L1b, el tiempo de CSPP y el de la ceniza, y la latencia total desde el inicio del escaneo.

## Requisitos en tahan

- CSPP Geo AIT 2.3.1 en `~lanotadm/csppgeo/cspp-geo-aitf-2.3`.
- Ambiente de Python en `~lanotadm/ceniza/venv` con las dependencias de `requirements.txt`.
- Efemérides en `/usr/local/share/lanot/skyfield/de421.bsp`.

## Prueba del 2026-10-18 (escaneo de 21:31 UTC)

| paso | tahan | cirrus (cadena completa) |
|---|---|---|
| CSPP hasta Cloud Phase | 89 s | ~5 min |
| ceniza | 8 s | — |

- Ceniza idéntica, píxel por píxel, a la calculada con las L2 de cirrus.
- ACM idéntico; ACTP con 1 píxel distinto de 3.75 millones.
- Latencia esperada en operación: ~4.8 min desde el inicio del escaneo (hoy ~8.3 min en cirrus).

Aún no está en el cron.
