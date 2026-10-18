#!/bin/bash
# Producto de ceniza CONUS de baja latencia, en tahan.
#
# Corre CSPP Geo AIT solo con lo que necesita el algoritmo (cmi, acm, actp) y en 4 segmentos,
# y luego detect_ash.py. No toca la cadena de cirrus: lee las L1b y el caché dinámico de
# CSPP del /data de cirrus, montado en tahan como /data1, y escribe todo en /data/ceniza/oper.
#
#   procesa_ceniza.sh                 el escaneo CONUS más reciente con las 16 bandas
#   procesa_ceniza.sh s20262911721    un escaneo concreto (sAAAAJJJHHMM)
#
# Por cada escaneo agrega una línea a $BASE/latencia_ceniza.csv con las horas de cada paso.
# Probado a mano el 2026-10-18. Alejandro Aguilar Sierra, asierra@unam.mx

L1B_DIR=/data1/input/abi/l1b/conus
BASE=/data/ceniza/oper
SALIDA=$BASE/conus
TCACHE=$BASE/aitf_temporal_cache
CSV=$BASE/latencia_ceniza.csv
CENIZA=/opt/LANOT_ceniza/detect_ash.py
PYTHON=$HOME/ceniza/venv/bin/python

export PATH=$HOME/csppgeo/cspp-geo-aitf-2.3:$PATH
export CSPP_GEO_AITF_CACHE=/data1/aitf_2_3_cache     # lo mantiene al día el cron de cirrus
export CSPP_GEO_AITF_ANCIL_TIMEOUT=7200

# Pasada mínima para la ceniza. Con 4 segmentos, ACM y ACTP salen idénticos a los de la
# corrida completa de cirrus (comparado píxel a píxel el 2026-10-18).
PRODUCTOS=${PRODUCTOS:-cmi,acm,actp}
FILAS_SEGMENTO=${FILAS_SEGMENTO:-375}

mkdir -p $BASE/tmp $SALIDA $TCACHE

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

# Una sola corrida por escaneo.
exec 9>"$BASE/tmp/.ceniza-$id.lock"
if ! flock -n 9; then
    echo "Aviso: ya hay una corrida en curso para $id."
    exit 0
fi
if ls $SALIDA/ceniza_${id#s}*.tif >/dev/null 2>&1; then
    echo "Aviso: $id ya fue procesado."
    exit 0
fi

l1b=( $L1B_DIR/*_${id}*.nc )
if [ ${#l1b[@]} -ne 16 ] || [ ! -e "${l1b[0]}" ]; then
    echo "Error: $id incompleto (${#l1b[@]} de 16 bandas)."
    exit 1
fi

t_l1b=$(stat -c %Z "${l1b[@]}" | sort -n | tail -1)   # llegada a cirrus de la última banda
t_ini=$(date +%s.%N)

mkdir -p "$work"
c01=$(ls $L1B_DIR/*C01*_${id}*.nc)
if ! aitf -o "$work" --cache-only --temporal-cache-dir $TCACHE \
          --products $PRODUCTOS --max-segment-rows $FILAS_SEGMENTO -q "$c01" > "$work/aitf.out" 2>&1; then
    echo "Error: aitf falló para $id; ver $work/aitf.out" >&2
    exit 1
fi
t_cspp=$(date +%s.%N)

if ! $PYTHON $CENIZA -p "$work" -m ${id#s} -o $SALIDA/ > "$work/ceniza.out" 2>&1; then
    echo "Error: detect_ash.py falló para $id; ver $work/ceniza.out" >&2
    exit 1
fi
t_fin=$(date +%s.%N)

# Inicio de escaneo (UTC) a partir del nombre: _sAAAAJJJHHMMSSs
s=$(basename "$c01" | grep -o '_s[0-9]\{14\}' | cut -c3-)
t0=$(date -u -d "${s:0:4}-01-01 +$((10#${s:4:3} - 1)) days ${s:7:2}:${s:9:2}:${s:11:2}" +%s).${s:13:1}

[ -s $CSV ] || echo "escaneo,llegada_cirrus_s,cspp_s,ceniza_s,total_s" > $CSV
awk -v id=$id -v t0=$t0 -v l=$t_l1b -v i=$t_ini -v c=$t_cspp -v f=$t_fin 'BEGIN {
    printf "%s,%.1f,%.1f,%.1f,%.1f\n", id, l - t0, c - i, f - c, f - t0 }' >> $CSV
tail -1 $CSV

# Limpieza: directorios de trabajo de más de una hora (ruta fija, nunca una variable).
find /data/ceniza/oper/tmp -mindepth 1 -maxdepth 1 -name 'conus-s*' -mmin +60 -exec rm -rf {} +
find /data/ceniza/oper/tmp -maxdepth 1 -name '.ceniza-s*.lock' -mmin +60 -delete
