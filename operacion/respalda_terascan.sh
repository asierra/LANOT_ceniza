#!/bin/bash
# Respaldo de los GeoTIFF de ceniza de TeraScan (región centromex) en tahan. Una vez al día por cron.
#
# Es la referencia para comparar con nuestra versión (doc/2026-11-05_comparacion_terascan.md).
# TeraScan los conserva desde el 2025-04-07, pero no sabemos hasta cuándo: aquí se copian tal
# cual (float32, sin recomprimir) y nunca se borran, aunque desaparezcan del origen.
#
#   respalda_terascan.sh          copia lo que falte
#
# Solo copia archivos con más de MIN_EDAD_MIN minutos, para no llevarse uno que TeraScan está
# escribiendo (con --ignore-existing ya no se corregiría). La primera corrida copia todo el
# archivo (~140 000 archivos, ~165 GB) con el ancho de banda limitado a BWLIMIT.
#
# Requisito: la cuenta que corre el script entra sin contraseña a TERASCAN (ssh con llave).
# lanotadm@tahan no entra; corre en el crontab de aguilars, que está en el grupo ash.
set -euo pipefail

TERASCAN=${TERASCAN:-teradm@132.247.103.142}
ORIGEN_DIR=${ORIGEN_DIR:-/opt/terascan/products/exportadas/geotiff/cenizas2/centromex}
DESTINO=${DESTINO:-/data/ceniza/terascan/centromex}
MIN_EDAD_MIN=${MIN_EDAD_MIN:-30}
BWLIMIT=${BWLIMIT:-20m}                  # para rsync --bwlimit (20 MB/s)

umask 0002
GRUPO=${GRUPO:-ash}                      # grupo de lo respaldado (setgid en las carpetas)
if [ ! -d "$DESTINO" ]; then
    mkdir -p "$DESTINO"
    chgrp "$GRUPO" "$DESTINO" "$(dirname "$DESTINO")" && chmod g+s "$DESTINO" "$(dirname "$DESTINO")" \
        || echo "AVISO: no pude poner el grupo $GRUPO en $DESTINO" >&2
fi

# Log mensual. En una terminal la salida se queda en pantalla; desde cron va al log.
# /var/log/lanot/ceniza es de lanotadm: con otra cuenta, el log va junto al respaldo.
LOGDIR=${LOGDIR:-/var/log/lanot/ceniza}
[ -w "$LOGDIR" ] || LOGDIR=$(dirname "$DESTINO")/log
if [ ! -t 1 ] && mkdir -p "$LOGDIR" 2>/dev/null; then
    exec >> "$LOGDIR/respalda_terascan_$(date -u +%Y%m).log" 2>&1
    find "$LOGDIR" -name 'respalda_terascan_*.log' -mtime +400 -delete
fi
log () { echo "$(date -u +%FT%TZ) $*"; }

# Una sola corrida a la vez (la primera puede durar horas).
exec 9>"$DESTINO/.respaldo.lock"
flock -n 9 || { log "ya hay un respaldo en curso; salgo"; exit 0; }

lista=$(mktemp)
trap 'rm -f "$lista"' EXIT

ssh -o BatchMode=yes -o ConnectTimeout=20 "$TERASCAN" \
    "find '$ORIGEN_DIR' -maxdepth 1 -type f -name '*.centromex.tif' -mmin +$MIN_EDAD_MIN -printf '%f\n'" \
    > "$lista" || { log "ERROR: no pude listar $TERASCAN:$ORIGEN_DIR"; exit 1; }

en_origen=$(wc -l < "$lista")
antes=$(find "$DESTINO" -maxdepth 1 -name '*.centromex.tif' | wc -l)

rsync -a --ignore-existing --bwlimit="$BWLIMIT" --timeout=600 \
    -e "ssh -o BatchMode=yes -o ConnectTimeout=20" \
    --files-from="$lista" "$TERASCAN:$ORIGEN_DIR/" "$DESTINO/" \
    || { log "ERROR: rsync terminó con código $?"; exit 1; }

despues=$(find "$DESTINO" -maxdepth 1 -name '*.centromex.tif' | wc -l)
log "ok | en origen $en_origen · copiados $((despues - antes)) · en respaldo $despues"
