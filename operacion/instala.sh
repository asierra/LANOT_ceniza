#!/bin/bash
# Instala o actualiza LANOT_ceniza en el servidor de operación, desde un clon del repositorio.
#
#   cd ~/src/LANOT_ceniza && git pull && operacion/instala.sh [DESTINO]
#
# DESTINO (por omisión /opt/lanot/ceniza) queda así:
#   .venv/                ambiente propio, creado con el Python del sistema (sin conda ni
#                         cuentas personales), con el paquete y sus dependencias
#   operacion/            procesa_ceniza.sh, vigila_ceniza.sh, crontab.ejemplo y README.md
#   VERSION               commit del que se instaló
#
# El clon puede estar en un home privado: DESTINO no depende de él después de instalar.
# Para actualizar, basta con git pull en el clon y volver a correr este script.
set -euo pipefail

RAIZ=$(cd "$(dirname "$0")/.." && pwd)
DESTINO=${1:-/opt/lanot/ceniza}
PYTHON_SISTEMA=${PYTHON_SISTEMA:-/usr/bin/python3}

[ -d "$DESTINO" ] && [ -w "$DESTINO" ] || {
    echo "Error: $DESTINO no existe o no tienes permiso de escritura. Una sola vez:" >&2
    echo "  sudo mkdir -p $DESTINO && sudo chown lanotadm:ash $DESTINO && sudo chmod 2775 $DESTINO" >&2
    exit 1
}
"$PYTHON_SISTEMA" -c 'import sys; assert sys.version_info >= (3, 10), "se requiere Python >= 3.10"'

# Los archivos instalados deben poder leerlos lanotadm y el grupo ash.
umask 0002

if [ ! -x "$DESTINO/.venv/bin/python" ]; then
    echo "Creando $DESTINO/.venv con $("$PYTHON_SISTEMA" --version)"
    "$PYTHON_SISTEMA" -m venv "$DESTINO/.venv"
fi
"$DESTINO/.venv/bin/pip" install -q --upgrade pip
"$DESTINO/.venv/bin/pip" install -q --upgrade --force-reinstall --no-deps "$RAIZ"
"$DESTINO/.venv/bin/pip" install -q "$RAIZ"          # dependencias que falten

mkdir -p "$DESTINO/operacion"
install -m 0775 "$RAIZ/operacion/procesa_ceniza.sh" "$RAIZ/operacion/vigila_ceniza.sh" "$DESTINO/operacion/"
install -m 0664 "$RAIZ/operacion/crontab.ejemplo" "$RAIZ/operacion/README.md" "$DESTINO/operacion/"
git -C "$RAIZ" describe --always --dirty --tags > "$DESTINO/VERSION" 2>/dev/null || echo desconocida > "$DESTINO/VERSION"

# Efemérides de Skyfield: detect_ash.py las busca en /usr/local/share/lanot/skyfield.
if [ ! -r /usr/local/share/lanot/skyfield/de421.bsp ]; then
    echo "AVISO: falta /usr/local/share/lanot/skyfield/de421.bsp (no está en el repo). Para descargarlo:" >&2
    echo "  sudo mkdir -p /usr/local/share/lanot/skyfield && sudo $DESTINO/.venv/bin/python -c \"from skyfield.api import Loader; Loader('/usr/local/share/lanot/skyfield')('de421.bsp')\"" >&2
fi

"$DESTINO/.venv/bin/lanot-detect-ash" --help > /dev/null
echo "Listo: $DESTINO (versión $(cat "$DESTINO/VERSION"))"
