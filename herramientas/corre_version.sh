#!/bin/bash
# Corre una versión de detect_ash.py (un commit, o el árbol de trabajo) sobre una lista de
# instantes y deja los GeoTIFF en una carpeta. Sirve para comparar versiones con
# herramientas/compara_salidas.py.
#
#   herramientas/corre_version.sh REF L2 SALIDA INSTANTE... [-- OPCIONES de detect_ash]
#
#   REF       commit (90ad79f, HEAD, ...) o "trabajo" para el árbol de trabajo actual
#   L2        carpeta con los NetCDF L2 (con --date-tree, la raíz del árbol AAAA/MM/DD)
#   SALIDA    carpeta para los GeoTIFF
#   INSTANTE  YYYYjjjHHMM; también se pueden pasar en un archivo con @lista.txt
#
# Ejemplo, la versión del artículo contra la actual en tres instantes recortados:
#   herramientas/corre_version.sh 90ad79f /datos/l2 /tmp/dic 20240580406 20240580411 -- --clip popocatepetl
#   herramientas/corre_version.sh HEAD    /datos/l2 /tmp/hoy 20240580406 20240580411 -- --clip popocatepetl
#   herramientas/compara_salidas.py /tmp/dic /tmp/hoy
#
# Cada instante se corre en un proceso aparte con las opciones largas que entienden todas
# las versiones (--path, --moment, --output); la de diciembre no acepta rangos.
# PYTHON elige el intérprete (por omisión, .venv/bin/python del repositorio).
set -euo pipefail

[ $# -ge 4 ] || { sed -n '2,20p' "$0"; exit 2; }
REPO=$(cd "$(dirname "$0")/.." && pwd)
ref=$1 l2=$(readlink -f "$2") salida=$(readlink -m "$3"); shift 3

instantes=() opciones=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    if [[ $1 == @* ]]; then mapfile -t -O ${#instantes[@]} instantes < "${1#@}"; else instantes+=("$1"); fi
    shift
done
[ "${1:-}" = "--" ] && { shift; opciones=("$@"); }

PYTHON=${PYTHON:-$REPO/.venv/bin/python}
SKYFIELD=${LANOT_SKYFIELD_DIR:-/usr/local/share/lanot/skyfield}
codigo=$(mktemp -d "${TMPDIR:-/tmp}/ceniza-$ref.XXXX")
trap 'rm -rf "$codigo"' EXIT

if [ "$ref" = trabajo ]; then
    cp "$REPO/detect_ash.py" "$codigo/"
else
    git -C "$REPO" show "$ref:detect_ash.py" > "$codigo/detect_ash.py"
fi

# Versiones anteriores a mayo de 2026 importan PIL y mapdrawer aunque solo los usan con
# --png. Módulos vacíos para que importen sin instalar nada.
mkdir -p "$codigo/PIL"
echo "Image = None" > "$codigo/PIL/__init__.py"
echo "class MapDrawer: pass" > "$codigo/mapdrawer.py"

# Las versiones viejas cargan de421.bsp del directorio de trabajo.
mkdir -p "$salida"
[ -e "$salida/de421.bsp" ] || ln -s "$SKYFIELD/de421.bsp" "$salida/de421.bsp"

echo "$ref ($(git -C "$REPO" rev-parse --short "${ref/trabajo/HEAD}")$([ "$ref" = trabajo ] && echo ', con cambios sin commit')) -> $salida"
fallas=0
for m in "${instantes[@]}"; do
    if ! (cd "$salida" && "$PYTHON" "$codigo/detect_ash.py" --path "$l2" --moment "$m" \
              --output "$salida/" "${opciones[@]}" > "$salida/$m.log" 2>&1); then
        fallas=$((fallas + 1)); echo "  falló $m (ver $salida/$m.log)"
    fi
done
rm -f "$salida/de421.bsp"
echo "${#instantes[@]} instantes, $fallas fallas"
