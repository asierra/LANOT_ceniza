#!/bin/bash
# Instala o actualiza el ambiente de LANOT_ceniza en el servidor de operación.
#
# Se corre desde el clon del repositorio (en tahan, /opt/lanot/ceniza):
#
#   cd /opt/lanot/ceniza && git pull && operacion/instala.sh
#
# Crea .venv dentro del clon con el Python del sistema, sin depender de conda ni
# de ninguna cuenta personal, e instala el paquete y sus dependencias. Después de un
# git pull basta con volver a correrlo.
set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/.." && pwd)
PYTHON_SISTEMA=${PYTHON_SISTEMA:-/usr/bin/python3}

"$PYTHON_SISTEMA" -c 'import sys; assert sys.version_info >= (3, 10), "se requiere Python >= 3.10"'

if [ ! -x "$RAIZ/.venv/bin/python" ]; then
    echo "Creando $RAIZ/.venv con $("$PYTHON_SISTEMA" --version)"
    "$PYTHON_SISTEMA" -m venv "$RAIZ/.venv"
fi
"$RAIZ/.venv/bin/pip" install -q --upgrade pip
"$RAIZ/.venv/bin/pip" install -q --upgrade "$RAIZ"

# Efemérides de Skyfield: detect_ash.py las busca en /usr/local/share/lanot/skyfield.
if [ ! -r /usr/local/share/lanot/skyfield/de421.bsp ]; then
    echo "AVISO: falta /usr/local/share/lanot/skyfield/de421.bsp (hay una copia en $RAIZ/de421.bsp)." >&2
fi

"$RAIZ/.venv/bin/lanot-detect-ash" --help > /dev/null
echo "Listo: $RAIZ/.venv/bin/lanot-detect-ash"
