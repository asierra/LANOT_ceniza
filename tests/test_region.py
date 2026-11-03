"""Regiones como puntos [lon, lat] y su rectángulo en la proyección GOES."""
import numpy as np
import pytest
from pyproj import CRS, Transformer

import detect_ash as d

GOES16 = CRS.from_proj4("+proj=geos +h=35786023 +lon_0=-75.0 +sweep=x "
                        "+a=6378137 +b=6356752.31414 +units=m +no_defs")
A_GOES = Transformer.from_crs("EPSG:4326", GOES16, always_xy=True)
CHILE = [[-86.2941, -46.4586], [-81.5787, -28.0659], [-48.4401, -29.3967], [-44.6973, -46.9981]]


def test_dos_esquinas_en_cualquier_orden():
    rect = [[-100.0, 18.0], [-97.0, 20.0]]
    esperado = [[-100, 18], [-97, 18], [-97, 20], [-100, 20]]
    for p in (rect, rect[::-1], [[-100.0, 20.0], [-97.0, 18.0]]):
        np.testing.assert_array_equal(d.vertices_region(p), esperado)
    assert d.limites_region(rect) == (-100, 18, -97, 20)


def test_poligono():
    np.testing.assert_array_equal(d.vertices_region(CHILE), CHILE)
    assert d.limites_region(CHILE) == (-86.2941, -46.9981, -44.6973, -28.0659)


@pytest.mark.parametrize("malo", [[[-100, 18]], [[-100, 18], [-100, 20]], [[-100, 18, 0], [-97, 20, 0]],
                                  [[-100, 18], [np.nan, 20]]])
def test_regiones_invalidas(malo):
    with pytest.raises(ValueError):
        d.vertices_region(malo)


def test_densifica():
    v = d.vertices_region([[0, 0], [1, 0.5]])
    pts = d.densifica(v, paso=0.1)
    # Contorno cerrado: pasa por cada vértice y ningún salto es mayor que el paso.
    for vert in v:
        assert (np.abs(pts - vert).max(axis=1) == 0).any()
    saltos = np.abs(np.diff(np.vstack([pts, pts[:1]]), axis=0)).max(axis=1)
    assert saltos.max() <= 0.1 + 1e-12


def test_regiones_de_mexico_sin_cambio():
    # Al noroeste del punto subsatelital, las esquinas SO y NE son los extremos en GOES:
    # el recorte nuevo coincide con el de antes (que solo transformaba esas dos).
    for puntos in d.CLIP_REGIONS.values():
        lon0, lat0, lon1, lat1 = d.limites_region(puntos)
        x0, y0 = A_GOES.transform(lon0, lat0)
        x1, y1 = A_GOES.transform(lon1, lat1)
        np.testing.assert_allclose(d.limites_goes(puntos, A_GOES), (x0, y0, x1, y1), atol=1e-6)


def test_chile_contiene_todo_el_contorno():
    # Chile cruza el meridiano del satélite y está al sur: dos esquinas no bastan.
    x0, y0, x1, y1 = d.limites_goes(CHILE, A_GOES)
    x, y = A_GOES.transform(*d.densifica(d.vertices_region(CHILE), paso=0.001).T)
    tol = 1.0  # m; un píxel mide unos 2 km
    assert x0 - tol <= x.min() and x.max() <= x1 + tol and y0 - tol <= y.min() and y.max() <= y1 + tol


def test_rectangulo_de_chile():
    # Con el rectángulo que contiene a Chile, el método de antes (solo esquinas SO y NE)
    # perdía más de 100 píxeles al oeste.
    lon0, lat0, lon1, lat1 = d.limites_region(CHILE)
    x0, _, _, _ = d.limites_goes([[lon0, lat0], [lon1, lat1]], A_GOES)
    xa, _ = A_GOES.transform(lon0, lat0)
    assert xa - x0 > 100 * 2004


def test_margen_agranda():
    p = d.CLIP_REGIONS["ashpaper"]
    x0, y0, x1, y1 = d.limites_goes(p, A_GOES)
    m0, n0, m1, n1 = d.limites_goes(p, A_GOES, margen=0.1)
    assert m0 < x0 and n0 < y0 and m1 > x1 and n1 > y1


def test_fuera_del_disco():
    with pytest.raises(ValueError, match="disco visible"):
        d.limites_goes([[100.0, 10.0], [110.0, 20.0]], A_GOES)
