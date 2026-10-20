#!/bin/bash
# Producto de ceniza de baja latencia a partir del escaneo CONUS, en tahan.
#
# Corre CSPP Geo AIT solo con lo que necesita el algoritmo (cmi, acm, actp) y en 4 segmentos,
# y luego detect_ash.py, recortado a la región RECORTE. No toca la cadena de cirrus: lee las
# L1b y el caché dinámico de CSPP del /data de cirrus, montado en tahan como /data1, y escribe
# todo en /data/ceniza/oper.
#
#   procesa_ceniza.sh                 el escaneo CONUS más reciente con las 16 bandas
#   procesa_ceniza.sh s20262911721    un escaneo concreto (sAAAAJJJHHMM)
#
# Por cada escaneo agrega una línea a $BASE/latencia_ceniza.csv con las horas de cada paso.
# Instalación y cron: operacion/README.md. Alejandro Aguilar Sierra, asierra@unam.mx

# Configuración. Todo se puede cambiar con variables de entorno (por ejemplo, en el crontab).
L1B_DIR=${L1B_DIR:-/data1/input/abi/l1b/conus}         # L1b CONUS de cirrus (su /data en /data1)
BASE=${BASE:-/data/ceniza/oper}                        # trabajo, caché temporal, salida y CSV
# Región de detect_ash.py (--clip). ashpapergeo: la región del artículo, en lat/lon (EPSG:4326).
# RECORTE= (vacío) genera el GeoTIFF CONUS completo, en proyección GOES (~9 s más por escaneo).
RECORTE=${RECORTE-ashpapergeo}
SALIDA=${SALIDA:-$BASE/${RECORTE:-conus}}              # GeoTIFF de ceniza
TCACHE=$BASE/aitf_temporal_cache                       # caché temporal propio de CSPP
CSV=$BASE/latencia_ceniza.csv
INSTALACION=${INSTALACION:-/opt/lanot/ceniza}          # donde instala operacion/instala.sh
CENIZA=$INSTALACION/.venv/bin/lanot-detect-ash
AITF_DIR=${AITF_DIR:-$HOME/csppgeo/cspp-geo-aitf-2.3}  # CSPP Geo AIT 2.3.1

export PATH=$AITF_DIR:$PATH
export CSPP_GEO_AITF_CACHE=${CSPP_GEO_AITF_CACHE:-/data1/aitf_2_3_cache}   # lo mantiene al día el cron de cirrus
export CSPP_GEO_AITF_ANCIL_TIMEOUT=7200

# Pasada mínima para la ceniza. Con 4 segmentos, ACM y ACTP salen idénticos a los de la
# corrida completa de cirrus (comparado píxel a píxel el 2026-10-18).
PRODUCTOS=${PRODUCTOS:-cmi,acm,actp}
FILAS_SEGMENTO=${FILAS_SEGMENTO:-375}

# Requisitos: mejor fallar aquí, con un mensaje claro, que a medio camino.
falta () { echo "Error: $*" >&2; exit 1; }
[[ "$BASE" == /?*/* ]]            || falta "BASE debe ser una ruta absoluta de al menos dos niveles ($BASE)."
[ -x "$AITF_DIR/aitf" ]           || falta "no encuentro CSPP Geo AIT en $AITF_DIR (ajusta AITF_DIR)."
[ -x "$CENIZA" ]                  || falta "no encuentro $CENIZA; instala con operacion/instala.sh desde el clon del repositorio."
[ -d "$L1B_DIR" ]                 || falta "no existe el directorio de L1b $L1B_DIR."
[ -d "$CSPP_GEO_AITF_CACHE" ]     || falta "no existe el caché dinámico de CSPP $CSPP_GEO_AITF_CACHE."

mkdir -p $BASE/tmp $SALIDA $TCACHE

# Log mensual. En una terminal la salida se queda en pantalla; desde cron va al log.
# Se conservan ~6 meses.
LOGDIR=${LOGDIR:-/var/log/lanot/ceniza}
if [ ! -t 1 ] && mkdir -p "$LOGDIR" 2>/dev/null; then
    exec >> "$LOGDIR/procesa_$(date -u +%Y%m).log" 2>&1
    find "$LOGDIR" -name 'procesa_*.log' -mtime +190 -delete
fi
log () { echo "$(date -u +%FT%TZ) $*"; }

if [ -n "$1" ]; then
    id=$1
else
    id=$(ls $L1B_DIR | grep C16 | tail -1 | cut -d_ -f4 | cut -c1-12)
fi
if [[ ! "$id" =~ ^s[0-9]{11}$ ]]; then
    echo "Usanza: $0 [sAAAAJJJHHMM]" >&2
    exit 2
fi

work=$BASE/tmp/conus-$id

# Una sola corrida por escaneo. La corrida de respaldo (x5:10) normalmente encuentra el
# escaneo en curso o ya procesado: sale sin escribir nada.
exec 9>"$BASE/tmp/.ceniza-$id.lock"
flock -n 9 || exit 0
ls $SALIDA/ceniza_${id#s}*.tif >/dev/null 2>&1 && exit 0

# Registro en el CSV: una línea por intento, con su estado (ok, incompleto, error_cspp,
# error_ceniza). Los tiempos que no se alcanzaron quedan vacíos. La primera vez agrega la
# columna estado a un CSV viejo (todas sus líneas fueron corridas exitosas).
CABECERA="escaneo,llegada_cirrus_s,cspp_s,ceniza_s,total_s,estado"
if [ ! -s $CSV ]; then
    echo "$CABECERA" > $CSV
elif ! head -1 $CSV | grep -q ',estado$'; then
    awk -v cab="$CABECERA" 'NR == 1 { print cab; next } { print $0 ",ok" }' $CSV > $CSV.tmp && mv $CSV.tmp $CSV
fi
t0=""; t_l1b=""; t_ini=""; t_cspp=""; t_fin=""
registra () {
    awk -v id=$id -v t0="$t0" -v l="$t_l1b" -v i="$t_ini" -v c="$t_cspp" -v f="$t_fin" -v e=$1 '
        function d(a, b) { return (a == "" || b == "") ? "" : sprintf("%.1f", a - b) }
        BEGIN { printf "%s,%s,%s,%s,%s,%s\n", id, d(l, t0), d(c, i), d(f, c), d(f, t0), e }' >> $CSV
    [ "$1" = ok ] || { mkdir -p "$work" && touch "$work/FALLO"; }
}

l1b=( $L1B_DIR/*_${id}*.nc )
c01=$(ls $L1B_DIR/*C01*_${id}*.nc 2>/dev/null)
if [ -n "$c01" ]; then
    # Inicio de escaneo (UTC) a partir del nombre: _sAAAAJJJHHMMSSs
    s=$(basename "$c01" | grep -o '_s[0-9]\{14\}' | cut -c3-)
    t0=$(date -u -d "${s:0:4}-01-01 +$((10#${s:4:3} - 1)) days ${s:7:2}:${s:9:2}:${s:11:2}" +%s).${s:13:1}
fi
if [ ${#l1b[@]} -ne 16 ] || [ ! -e "${l1b[0]}" ] || [ -z "$c01" ]; then
    log "Error: $id incompleto ($( [ -e "${l1b[0]}" ] && echo ${#l1b[@]} || echo 0) de 16 bandas)."
    registra incompleto
    exit 1
fi

t_l1b=$(stat -c %Z "${l1b[@]}" | sort -n | tail -1)   # llegada a cirrus de la última banda
t_ini=$(date +%s.%N)

mkdir -p "$work"
if ! aitf -o "$work" --cache-only --temporal-cache-dir $TCACHE \
          --products $PRODUCTOS --max-segment-rows $FILAS_SEGMENTO -q "$c01" > "$work/aitf.out" 2>&1; then
    t_cspp=$(date +%s.%N)
    log "Error: aitf falló para $id; ver $work/aitf.out"
    registra error_cspp
    exit 1
fi
t_cspp=$(date +%s.%N)

$CENIZA -p "$work" -m ${id#s} ${RECORTE:+--clip $RECORTE} -o $SALIDA/ > "$work/ceniza.out" 2>&1
codigo=$?
t_fin=$(date +%s.%N)
if [ $codigo -ne 0 ] || ! ls $SALIDA/ceniza_${id#s}*.tif >/dev/null 2>&1; then
    # Código 3: faltan productos L2, es decir, CSPP terminó sin generar todo lo necesario.
    estado=error_ceniza; [ $codigo -eq 3 ] && estado=error_cspp
    log "Error: detect_ash.py falló para $id (código $codigo, $estado); ver $work/ceniza.out"
    registra $estado
    exit 1
fi

registra ok
log "$(tail -1 $CSV)"

# Limpieza: directorios de trabajo de más de una hora (BASE ya se validó arriba). Los de
# corridas fallidas se conservan un día para poder revisarlos.
find "$BASE/tmp" -mindepth 1 -maxdepth 1 -name 'conus-s*' -mmin +60 ! -exec test -e '{}/FALLO' \; -exec rm -rf {} +
find "$BASE/tmp" -mindepth 1 -maxdepth 1 -name 'conus-s*' -mmin +1440 -exec rm -rf {} +
find "$BASE/tmp" -maxdepth 1 -name '.ceniza-s*.lock' -mmin +60 -delete
