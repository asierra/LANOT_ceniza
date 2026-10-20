#!/bin/bash
# Vigila la cadena de ceniza de baja latencia en tahan. Cada 15 min por cron.
#
# Revisa la última hora y deja el resultado en $BASE/state/estado.json. Solo cuando el
# estado cambia (ok -> falla o falla -> ok) agrega una línea a $BASE/state/eventos.log,
# que es lo que hay que revisar. No manda avisos: si después se quiere correo o
# mensajería, basta con leer eventos.log.
#
# Fallas:
#   sin_producto      el GeoTIFF más reciente tiene más de MAX_EDAD_MIN minutos
#   escaneos_perdidos escaneos de la última hora con las 16 bandas y sin GeoTIFF
#   errores           escaneos de la última hora cuyo último intento en el CSV no fue ok
#   latencia_alta     p95 de la latencia de la última hora mayor que MAX_P95_S
#
# Misma configuración que procesa_ceniza.sh (variables de entorno).
set -uo pipefail

L1B_DIR=${L1B_DIR:-/data1/input/abi/l1b/conus}
BASE=${BASE:-/data/ceniza/oper}
RECORTE=${RECORTE-ashpapergeo}
SALIDA=${SALIDA:-$BASE/${RECORTE:-conus}}
CSV=$BASE/latencia_ceniza.csv
ESTADO_DIR=$BASE/state
MAX_EDAD_MIN=${MAX_EDAD_MIN:-15}
MAX_P95_S=${MAX_P95_S:-360}

mkdir -p "$ESTADO_DIR"
ahora=$(date -u +%s)
fallas=()

# Producto más reciente
ultimo=$(ls -t "$SALIDA"/ceniza_*.tif 2>/dev/null | head -1)
if [ -n "$ultimo" ]; then
    edad_min=$(( (ahora - $(stat -c %Y "$ultimo")) / 60 ))
    [ $edad_min -gt $MAX_EDAD_MIN ] && fallas+=("sin_producto")
else
    edad_min=-1
    fallas+=("sin_producto")
fi

# Escaneos de la última hora (inicio entre hace 65 y hace 10 min) con C16 y sin GeoTIFF
perdidos=()
if [ -d "$L1B_DIR" ]; then
    desde=$(date -u -d @$((ahora - 65 * 60)) +%Y%j%H%M)
    hasta=$(date -u -d @$((ahora - 10 * 60)) +%Y%j%H%M)
    for id in $(ls "$L1B_DIR" | grep C16 | grep -o '_s[0-9]\{11\}' | cut -c3- | sort -u); do
        [[ "$id" > "$desde" || "$id" == "$desde" ]] && [[ "$id" < "$hasta" || "$id" == "$hasta" ]] || continue
        ls "$SALIDA"/ceniza_${id}*.tif >/dev/null 2>&1 || perdidos+=("s$id")
    done
fi
[ ${#perdidos[@]} -gt 0 ] && fallas+=("escaneos_perdidos")

# Errores y latencia de la última hora, del CSV (escaneo, ..., total_s, estado). Cuenta
# solo el último intento de cada escaneo: un "incompleto" que la corrida de respaldo
# resolvió no es error.
read -r errores p95 n_ok < <(awk -F, -v desde="s$(date -u -d @$((ahora - 3600)) +%Y%j%H%M)" '
    NR == 1 { for (i = 1; i <= NF; i++) col[$i] = i; next }
    $1 >= desde { est[$1] = ("estado" in col) ? $col["estado"] : "ok"; tot[$1] = $col["total_s"] }
    END {
        for (id in est) {
            if (est[id] != "ok") err++
            else if (tot[id] != "") t[++n] = tot[id] + 0
        }
        # p95 por rango más cercano
        for (i = 2; i <= n; i++) { v = t[i]; for (j = i - 1; j >= 1 && t[j] > v; j--) t[j + 1] = t[j]; t[j + 1] = v }
        k = int(0.95 * n + 0.999); if (k < 1) k = 1
        printf "%d %s %d\n", err, (n ? t[k] : "-"), n
    }' "$CSV" 2>/dev/null || echo "0 - 0")
[ "${errores:-0}" -gt 0 ] && fallas+=("errores")
[ "${p95:--}" != - ] && awk -v p="$p95" -v m="$MAX_P95_S" 'BEGIN { exit !(p > m) }' && fallas+=("latencia_alta")

estado=ok
[ ${#fallas[@]} -gt 0 ] && estado=falla
lista () { local out=""; for x in "$@"; do out+="${out:+,}\"$x\""; done; echo "[$out]"; }

cat > "$ESTADO_DIR/estado.json.tmp" <<EOF
{
  "estado": "$estado",
  "fallas": $(lista "${fallas[@]}"),
  "revisado_utc": "$(date -u -d @$ahora +%Y-%m-%dT%H:%M:%SZ)",
  "ultimo_producto": "$(basename "${ultimo:-}")",
  "edad_ultimo_producto_min": $edad_min,
  "ultima_hora": {
    "escaneos_ok": ${n_ok:-0},
    "errores": ${errores:-0},
    "escaneos_perdidos": $(lista "${perdidos[@]}"),
    "latencia_p95_s": $([ "${p95:--}" = - ] && echo null || echo "$p95")
  }
}
EOF
mv "$ESTADO_DIR/estado.json.tmp" "$ESTADO_DIR/estado.json"

# Evento solo si cambió el estado o la lista de fallas
resumen="$estado ${fallas[*]:-}"
anterior=$(cat "$ESTADO_DIR/.ultimo_resumen" 2>/dev/null || echo "")
if [ "$resumen" != "$anterior" ]; then
    echo "$(date -u -d @$ahora +%Y-%m-%dT%H:%M:%SZ) ${resumen% } | ultimo=$(basename "${ultimo:-ninguno}") edad=${edad_min}min errores=${errores:-0} perdidos=${#perdidos[@]} p95=${p95:-?}s" \
        >> "$ESTADO_DIR/eventos.log"
    echo "$resumen" > "$ESTADO_DIR/.ultimo_resumen"
fi
