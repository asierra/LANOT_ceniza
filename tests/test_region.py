"""Regiones como puntos [lon, lat]: su rectángulo en la proyección GOES y la máscara de
los polígonos."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from affine import Affine
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


# --- Polígonos: lo de afuera queda en 255 ----------------------------------------------

RAIZ = Path(__file__).resolve().parents[1]
L2 = RAIZ / "tests" / "datos" / "l2"
VILLARRICA = d.carga_perfil("villarrica")
DENTRO = [(-71.93, -39.42), (-83.0, -45.0), (-50.0, -30.0)]   # el volcán y dos cerca de esquinas
FUERA = [(-83.0, -30.0), (-45.5, -40.0), (-60.0, -46.9)]      # junto a los bordes oeste, este y sur, por fuera


def test_poligono_en_malla_goes():
    x0, y0, x1, y1 = d.limites_goes(VILLARRICA.region, A_GOES)
    res = 2004.0
    t = Affine(res, 0, x0, 0, -res, y1)
    forma = (int(np.ceil((y1 - y0) / res)), int(np.ceil((x1 - x0) / res)))
    fuera = d.fuera_del_poligono(VILLARRICA.region, forma, t, crs=GOES16)
    for lonlat, esperado in [(q, False) for q in DENTRO] + [(q, True) for q in FUERA]:
        col, fila = ~t @ A_GOES.transform(*lonlat)
        assert 0 <= fila < forma[0] and 0 <= col < forma[1], lonlat
        assert fuera[int(fila), int(col)] == esperado, lonlat
    assert 0.1 < fuera.mean() < 0.5


def test_poligono_en_malla_latlon():
    lon0, lat0, lon1, lat1 = d.limites_region(VILLARRICA.region)
    t = Affine(0.02, 0, lon0, 0, -0.02, lat1)
    forma = (int(np.ceil((lat1 - lat0) / 0.02)), int(np.ceil((lon1 - lon0) / 0.02)))
    fuera = d.fuera_del_poligono(VILLARRICA.region, forma, t)
    for lonlat, esperado in [(q, False) for q in DENTRO] + [(q, True) for q in FUERA]:
        col, fila = ~t @ lonlat
        assert 0 <= fila < forma[0] and 0 <= col < forma[1], lonlat
        assert fuera[int(fila), int(col)] == esperado, lonlat


def test_resuelve_region():
    popo = d.carga_perfil("popocatepetl")
    assert d.resuelve_region(None, popo) == (None, False)
    assert d.resuelve_region("ashpapergeo", popo) == (d.CLIP_REGIONS["ashpaper"], True)
    assert d.resuelve_region("ashpaper", popo, geo=True) == (d.CLIP_REGIONS["ashpaper"], True)
    assert d.resuelve_region("perfil", popo) == (d.CLIP_REGIONS["ashpaper"], False)
    assert d.resuelve_region("perfilgeo", VILLARRICA) == (VILLARRICA.region, True)
    with pytest.raises(ValueError, match="--geo"):
        d.resuelve_region(None, popo, geo=True)
    with pytest.raises(ValueError, match="no reconocida"):
        d.resuelve_region("chile", popo)


TRIANGULO = [[-100.1, 18.4], [-97.0, 18.4], [-98.5, 20.4]]


@pytest.fixture(scope="module")
def efemerides():
    return d.carga_efemerides()


@pytest.mark.parametrize("geo", [False, True])
def test_triangulo_en_datos_reales(tmp_path, efemerides, geo):
    eph, ts = efemerides
    instante = d.normalize_moment("20190601332")
    lon0, lat0, lon1, lat1 = d.limites_region(TRIANGULO)
    salidas = {}
    for nombre, region in [("triangulo", TRIANGULO), ("rectangulo", [[lon0, lat0], [lon1, lat1]])]:
        ruta = tmp_path / f"{nombre}.tif"
        d.process_instant(L2, instante, ruta, clip_region=region, geo=geo, eph=eph, ts=ts, escribe_qml=False)
        with rasterio.open(ruta) as f:
            salidas[nombre] = (f.read(1), f.transform, f.crs)
    (tri, t_tri, crs), (rect, t_rect, _) = salidas["triangulo"], salidas["rectangulo"]
    fuera = tri == d.SIN_DATOS
    assert 0.2 < fuera.mean() < 0.8
    if geo:
        # misma malla lat/lon (el rectángulo que contiene a la región)
        assert tri.shape == rect.shape and t_tri == t_rect
        mismo = rect
    else:
        # En GOES el triángulo se recorta con su propio rectángulo, más chico: se compara la
        # parte común, sin las 2 filas y columnas de la orilla, donde el kernel de 5 ve
        # vecinos distintos.
        dc, df = (round(v) for v in ~t_rect @ (t_tri.c, t_tri.f))
        mismo = rect[df:df + tri.shape[0], dc:dc + tri.shape[1]]
        assert mismo.shape == tri.shape
        fuera[:2] = fuera[-2:] = True
        fuera[:, :2] = fuera[:, -2:] = True
    np.testing.assert_array_equal(tri[~fuera], mismo[~fuera])
    assert (mismo[tri == d.SIN_DATOS] != d.SIN_DATOS).any()
    # adentro: la punta norte y el centro; afuera: a los lados, a media altura
    if geo:
        punto = lambda lon, lat: tuple(int(v) for v in (~t_tri @ (lon, lat))[::-1])
    else:
        a = Transformer.from_crs("EPSG:4326", d.CRS.from_wkt(crs.to_wkt()), always_xy=True)
        punto = lambda lon, lat: tuple(int(v) for v in (~t_tri @ a.transform(lon, lat))[::-1])
    assert tri[punto(-98.5, 20.2)] != d.SIN_DATOS and tri[punto(-98.5, 19.5)] != d.SIN_DATOS
    assert tri[punto(-99.9, 19.5)] == d.SIN_DATOS and tri[punto(-97.2, 19.5)] == d.SIN_DATOS


def corre(*args, cwd):
    return subprocess.run([sys.executable, str(RAIZ / "detect_ash.py"), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=120)


def test_cli_clip_perfil_y_geo(tmp_path):
    base = ["--path", str(L2), "-m", "20190601332", "--sin-qml"]
    for carpeta, extra in [("perfil", ["--clip", "perfil"]), ("nombre", ["--clip", "ashpaper"]),
                           ("geo", ["--clip", "popocatepetl", "--geo"]), ("sufijo", ["--clip", "popocatepetlgeo"])]:
        (tmp_path / carpeta).mkdir()
        r = corre(*base, *extra, "-o", f"{tmp_path / carpeta}/", cwd=tmp_path)
        assert r.returncode == 0, r.stdout + r.stderr
    lee = lambda ruta: rasterio.open(ruta).read(1)
    np.testing.assert_array_equal(lee(tmp_path / "perfil/ceniza_20190601332.tif"),
                                  lee(tmp_path / "nombre/ceniza_20190601332.tif"))
    np.testing.assert_array_equal(lee(tmp_path / "geo/ceniza_20190601332_geo.tif"),
                                  lee(tmp_path / "sufijo/ceniza_20190601332_geo.tif"))


def test_cli_geo_sin_clip(tmp_path):
    assert corre("--path", str(L2), "-m", "20190601332", "--geo", cwd=tmp_path).returncode == 2
