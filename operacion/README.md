# Operación de baja latencia (tahan)

`procesa_ceniza.sh` genera el producto de ceniza de cada escaneo CONUS sin esperar a la cadena L2 completa de cirrus:

1. Lee las L1b CONUS que cirrus trae de la estación (`/data1/input/abi/l1b/conus`, que es el `/data` de cirrus montado en tahan).
2. Corre CSPP Geo AIT solo con `cmi,acm,actp` y en 4 segmentos (`--max-segment-rows 375`). Usa el caché dinámico de cirrus (`/data1/aitf_2_3_cache`) y un caché temporal propio (`/data/ceniza/oper/aitf_temporal_cache`).
3. Corre `lanot-detect-ash` con 16 procesos, recortado a la región del artículo en lat/lon (`--clip ashpapergeo`), y deja el GeoTIFF en `/data/ceniza/oper/ashpapergeo/`. Con `RECORTE=` (vacío) genera en su lugar el CONUS completo en proyección GOES, en `/data/ceniza/oper/conus/` (~9 s más por escaneo; el recorte tarda ~0.5 s).
4. Agrega a `/data/ceniza/oper/latencia_ceniza.csv` el tiempo de cada paso y la latencia total desde el inicio del escaneo.

## Instalación

El código se clona en `~/src` de quien instala y se instala en `/opt/lanot/ceniza`, con su propio ambiente de Python (`.venv`, creado con el Python del sistema; no depende de conda ni de ninguna cuenta personal). Después de instalar, `/opt/lanot/ceniza` no depende del clon.

```bash
# Una sola vez: /opt/lanot es de root. El grupo ash puede instalar y actualizar.
sudo mkdir -p /opt/lanot/ceniza
sudo chown lanotadm:ash /opt/lanot/ceniza
sudo chmod 2775 /opt/lanot/ceniza

# Clonar e instalar (con cualquier usuario del grupo ash)
git clone git@github.com:asierra/LANOT_ceniza.git ~/src/LANOT_ceniza
cd ~/src/LANOT_ceniza && operacion/instala.sh            # destino por omisión: /opt/lanot/ceniza
```

Para actualizar:

```bash
cd ~/src/LANOT_ceniza && git pull && operacion/instala.sh
```

`/opt/lanot/ceniza/VERSION` dice de qué commit se instaló.

### Requisitos en el servidor

| requisito | dónde | variable para cambiarlo |
|---|---|---|
| Python ≥ 3.10 del sistema | `/usr/bin/python3` | `PYTHON_SISTEMA` (en `instala.sh`) |
| CSPP Geo AIT 2.3.1 | `~lanotadm/csppgeo/cspp-geo-aitf-2.3` | `AITF_DIR` |
| L1b CONUS | `/data1/input/abi/l1b/conus` | `L1B_DIR` |
| Caché dinámico de CSPP | `/data1/aitf_2_3_cache` | `CSPP_GEO_AITF_CACHE` |
| Efemérides de Skyfield | `/usr/local/share/lanot/skyfield/de421.bsp` | — (no están en el repo; `instala.sh` dice cómo descargarlas si faltan) |
| Directorio de trabajo y salida | `/data/ceniza/oper` (grupo `ash`) | `BASE`, `SALIDA` |
| Región del recorte | `ashpapergeo` (las regiones están en `detect_ash.py`) | `RECORTE` |

`procesa_ceniza.sh` revisa todo esto al arrancar y avisa qué falta.

## Prueba a mano

```bash
/opt/lanot/ceniza/operacion/procesa_ceniza.sh                  # el escaneo más reciente con las 16 bandas
/opt/lanot/ceniza/operacion/procesa_ceniza.sh s20262912131     # uno concreto
```

La primera corrida con el caché temporal vacío funciona, pero la máscara de nubes usa los escaneos anteriores; los resultados quedan iguales a los de cirrus después de unos cuantos escaneos (o copiando al caché los archivos CONUS recientes de `/data1/aitf_2_3_temporal_cache`).

## Cron

Ver `crontab.ejemplo`. cirrus trae las L1b a las x4:20 (llegan a la estación entre x4:10 y x4:15); la ceniza corre a las x4:30, con una segunda corrida de respaldo a las x5:10 para escaneos que lleguen tarde. Si un escaneo ya se procesó, el script sale sin hacer nada.

## Prueba del 2026-10-18 (escaneo de 21:31 UTC)

| paso | tahan (esta pasada) | cirrus (cadena completa) |
|---|---|---|
| CSPP hasta Cloud Phase | 89 s | ~5 min |
| ceniza | 8–9 s | — |

- Ceniza idéntica, píxel por píxel, a la calculada con las L2 completas de cirrus.
- ACM idéntico; ACTP con 1 píxel distinto de 3.75 millones.
- `--jobs 16` da el mismo resultado y el mismo tiempo que los 62 procesos por omisión; con 8 sube a 15 s.
- Latencia esperada en operación: ~4.8 min desde el inicio del escaneo (~8.3 min en cirrus).
