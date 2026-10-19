"""Regresión con tres recortes reales alrededor del Popocatépetl (tests/datos/l2):

    20240580406  2024-02-27 04:06 UTC  noche
    20190601332  2019-03-01 13:32 UTC  crepúsculo
    20190601437  2019-03-01 14:37 UTC  día

La salida esperada (tests/datos/esperado) es la del código vigente. Si un cambio la
altera a propósito, se regenera con ACTUALIZA_ESPERADOS=1 pytest tests/test_regresion.py
y la diferencia se explica en el commit.

Los recortes se hicieron con herramientas/genera_fixture.py (región 'popocatepetl').
"""
import os
from pathlib import Path

import numpy as np
import pytest
import rasterio

import detect_ash

DATOS = Path(__file__).parent / "datos"
INSTANTES = ["20240580406", "20190601332", "20190601437"]


@pytest.fixture(scope="module")
def efemerides():
    from skyfield.api import Loader
    loader = Loader(detect_ash.SKYFIELD_DIR if hasattr(detect_ash, "SKYFIELD_DIR")
                    else "/usr/local/share/lanot/skyfield")
    return loader("de421.bsp"), loader.timescale()


@pytest.mark.parametrize("instante", INSTANTES)
def test_regresion(instante, efemerides, tmp_path):
    eph, ts = efemerides
    salida = tmp_path / f"ceniza_{instante}.tif"
    detect_ash.process_instant(DATOS / "l2", detect_ash.normalize_moment(instante), salida, eph=eph, ts=ts)
    assert salida.exists(), "no se generó el GeoTIFF"

    esperado = DATOS / "esperado" / salida.name
    if os.environ.get("ACTUALIZA_ESPERADOS"):
        esperado.parent.mkdir(exist_ok=True)
        esperado.write_bytes(salida.read_bytes())
        pytest.skip("esperado regenerado")

    with rasterio.open(salida) as a, rasterio.open(esperado) as b:
        assert a.crs == b.crs
        assert a.transform.almost_equals(b.transform)
        va, vb = a.read(1), b.read(1)
        assert a.colormap(1) == b.colormap(1)
    distintos = int((va != vb).sum())
    assert distintos == 0, f"{distintos} píxeles distintos; clases: {np.unique(va, return_counts=True)}"


def test_los_casos_tienen_ceniza():
    """Que los recortes sigan siendo útiles: cada uno debe tener píxeles con ceniza."""
    for instante in INSTANTES:
        with rasterio.open(DATOS / "esperado" / f"ceniza_{instante}.tif") as d:
            v = d.read(1)
        assert np.isin(v, [1, 2, 3]).sum() > 0, instante
