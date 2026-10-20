"""Códigos de salida de lanot-detect-ash (P4): 0 bien, 1 error al procesar, 2 uso, 3 faltan datos."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
L2 = RAIZ / "tests" / "datos" / "l2"


def corre(*args, cwd):
    return subprocess.run([sys.executable, str(RAIZ / "detect_ash.py"), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=120)


def test_ok(tmp_path):
    r = corre("--path", str(L2), "-m", "20190601332", "-o", f"{tmp_path}/", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (tmp_path / "ceniza_20190601332.tif").exists()


def test_faltan_datos(tmp_path):
    r = corre("--path", str(L2), "-m", "20190601337", "-o", f"{tmp_path}/", cwd=tmp_path)
    assert r.returncode == 3


def test_rango_con_un_instante_sin_datos(tmp_path):
    # 13:32 tiene datos, 13:37 no: se procesa lo que hay y se reporta lo que faltó.
    r = corre("--path", str(L2), "-m", "20190601332-1337", "-o", f"{tmp_path}/", cwd=tmp_path)
    assert r.returncode == 3
    assert (tmp_path / "ceniza_20190601332.tif").exists()


@pytest.mark.parametrize("instante", ["2019", "20190601332-25"])
def test_uso(tmp_path, instante):
    assert corre("--path", str(L2), "-m", instante, cwd=tmp_path).returncode == 2


def test_dry_run(tmp_path):
    assert corre("--path", str(L2), "-m", "20190601332", "--dry-run", cwd=tmp_path).returncode == 0
    assert corre("--path", str(L2), "-m", "20190601337", "--dry-run", cwd=tmp_path).returncode == 3


def test_error_al_procesar(tmp_path):
    datos = tmp_path / "l2"
    shutil.copytree(L2, datos)
    c13 = next(datos.glob("*CMIPC-M3C13_G16_s20190601332*"))
    c13.write_bytes(c13.read_bytes()[:500])  # NetCDF truncado
    r = corre("--path", str(datos), "-m", "20190601332", "-o", f"{tmp_path}/", cwd=tmp_path)
    assert r.returncode == 1
