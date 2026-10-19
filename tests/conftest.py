import sys
from pathlib import Path

# detect_ash.py es un módulo suelto en la raíz del repositorio.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
