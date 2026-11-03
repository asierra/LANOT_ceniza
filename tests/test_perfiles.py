"""Perfiles de umbrales (perfiles/*.toml) y su lectura en detect_ash.

- Cada perfil del repositorio se lee y valida.
- classify_ash usa cada valor del perfil: cambiar cualquiera (umbral, celda de la tabla de
  fase, fase de nube) cambia la clasificación de una escena sintética.
- La validación es estricta: claves de más o de menos y valores sin sentido son error.
"""
import copy
import hashlib
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
import pytest
import rasterio

import detect_ash

RAIZ = Path(__file__).parents[1]
PERFILES = RAIZ / "perfiles"
L2 = RAIZ / "tests" / "datos" / "l2"
CLASES = ["sin_ceniza", "ca", "hap", "lap"]


def lee(nombre):
    with open(PERFILES / f"{nombre}.toml", "rb") as f:
        return tomllib.load(f)


def escena(semilla, n=80, malla=True):
    """Bandas sintéticas alrededor de los umbrales. Con malla=True los deltas caen en
    múltiplos de 0.25, así que hay píxeles justo en cada límite (0, −0.5, −1, −1.5, 1.5, 2)."""
    rng = np.random.default_rng(semilla)
    u = lambda a, b: rng.uniform(a, b, (n, n))
    # En la mitad derecha, un tercio de ΔT1 alto sube la media y la σ locales, para que
    # el kernel marque HAP; la mitad izquierda ejercita las pruebas por umbrales.
    alto = (rng.random((n, n)) < 0.35) & (np.arange(n) >= n // 2)
    d1 = np.where(alto, u(3, 6), u(-2, 3))
    d2, d3 = u(-2.5, 1.5), u(-1, 4)
    if malla:
        d1, d2, d3 = (np.round(d * 4) / 4 for d in (d1, d2, d3))
    c13 = np.where(rng.random((n, n)) < 0.1, 273.15, u(255, 290))
    c04 = np.where(rng.random((n, n)) < 0.1, 0.002, u(0, 0.004))
    sza = rng.choice([60.0, 69.9, 70.0, 77.0, 85.0, 85.1, 100.0], (n, n))
    f32 = lambda a: a.astype(np.float32)
    return dict(c04=f32(c04), c07=f32(c13 + d3), c11=f32(c13 + d2), c13=f32(c13), c15=f32(c13 - d1),
                phase=f32(rng.integers(0, 6, (n, n))), sza=f32(sza),
                valid_data_mask=rng.random((n, n)) > 0.02)


@pytest.mark.parametrize("nombre", ["popocatepetl", "villarrica"])
def test_perfiles_del_repositorio(nombre):
    p = detect_ash.carga_perfil(nombre)
    assert p.nombre == nombre
    assert p.sha256 == hashlib.sha256((PERFILES / f"{nombre}.toml").read_bytes()).hexdigest()


def test_popocatepetl():
    p = detect_ash.carga_perfil("popocatepetl")
    assert p.estado == "operacion" and p.dominio == "C" and p.region == "ashpaper"
    assert p.fases_nube == (3, 4)  # mixta y hielo
    assert detect_ash.perfil_por_omision() == p


def test_por_ruta(tmp_path):
    ruta = tmp_path / "otro.toml"
    ruta.write_bytes((PERFILES / "popocatepetl.toml").read_bytes())
    assert detect_ash.carga_perfil(ruta) == detect_ash.carga_perfil("popocatepetl")


def test_la_escena_ejercita_todas_las_salidas():
    assert set(np.unique(detect_ash.classify_ash(**escena(1)))) == {0, 1, 2, 3, 6, 255}


def variantes():
    """(descripción, función que cambia un valor del perfil leído del TOML)."""
    base = lee("popocatepetl")

    def suma(ruta, delta):
        def f(p):
            d = p
            for k in ruta[:-1]:
                d = d[k]
            d[ruta[-1]] += delta
        return f

    for seccion in ["iluminacion", "kernel", "refinamiento_hap", "filtro_dt3"]:
        for clave, v in base[seccion].items():
            yield f"{seccion}.{clave}", suma([seccion, clave], 2 if isinstance(v, int) else 0.25)
    for bloque in detect_ash.BLOQUES:
        for clase in ("ca", "hap"):
            for clave in base[bloque][clase]:
                delta = 0.001 if clave == "r137_min" else 0.25
                yield f"{bloque}.{clase}.{clave}", suma([bloque, clase, clave], delta)
    for clase in ("ca", "hap", "lap"):
        for fase, res in base["fase"][clase].items():
            otra = CLASES[(CLASES.index(res) + 1) % len(CLASES)]
            yield f"fase.{clase}.{fase}", lambda p, c=clase, f=fase, o=otra: p["fase"][c].__setitem__(f, o)
    for fase in detect_ash.FASES:
        def cambia_nube(p, fase=fase):
            nube = p["fase"]["nube"]
            nube.remove(fase) if fase in nube else nube.append(fase)
        yield f"fase.nube {fase}", cambia_nube


VARIANTES = list(variantes())
ESCENAS = [escena(1), escena(2), escena(3, malla=False)]


def test_hay_cincuenta_y_seis_variantes():
    # 32 números, 18 celdas de la tabla de fase y 6 fases que pueden o no ser nube
    assert len(VARIANTES) == 56


@pytest.mark.parametrize("cambio", [f for _, f in VARIANTES], ids=[d for d, _ in VARIANTES])
def test_classify_ash_usa_cada_valor(cambio):
    p = lee("popocatepetl")
    cambio(p)
    modificado = detect_ash.perfil_de_dict(p)
    # Algunos valores afectan pocos píxeles: basta con que cambie uno en alguna de las escenas.
    assert any((detect_ash.classify_ash(**datos) != detect_ash.classify_ash(**datos, perfil=modificado)).any()
               for datos in ESCENAS)


def sin(p, *ruta):
    d = p
    for k in ruta[:-1]:
        d = d[k]
    del d[ruta[-1]]


@pytest.mark.parametrize("cambio,mensaje", [
    (lambda p: p["kernel"].__setitem__("tamanio", 5), "desconocidas"),
    (lambda p: sin(p, "dia", "hap", "dt2_min"), "faltan"),
    (lambda p: sin(p, "fase"), "faltan"),
    (lambda p: p["kernel"].__setitem__("tamano", 4), "impar"),
    (lambda p: p["noche"]["ca"].__setitem__("dt1_max", "0"), "número"),
    (lambda p: p["iluminacion"].__setitem__("dia_max", 90.0), "dia_max"),
    (lambda p: p["refinamiento_hap"].__setitem__("lap_dt2_min", 0.0), "lap_dt2_min"),
    (lambda p: p["fase"]["hap"].__setitem__("agua", "nube"), "no es clase"),
    (lambda p: p["fase"].__setitem__("nube", ["granizo"]), "nube"),
    (lambda p: p["perfil"].__setitem__("estado", "probando"), "estado"),
    (lambda p: p["region"].__setitem__("dominio", "M"), "dominio"),
    (lambda p: p["region"].__setitem__("recorte", "chile"), "recorte"),
    (lambda p: p["region"].__setitem__("puntos", [[-100, 18], [-97, 20]]), "uno de los dos"),
    (lambda p: p["region"]["volcan"].__setitem__("lat", 30.0), "fuera de la región"),
])
def test_errores(cambio, mensaje):
    p = lee("popocatepetl")
    cambio(p)
    with pytest.raises(ValueError, match=mensaje):
        detect_ash.perfil_de_dict(p)


def test_volcan_fuera_del_poligono():
    p = lee("villarrica")
    p["region"]["volcan"]["lon"] = -40.0
    with pytest.raises(ValueError, match="fuera de la región"):
        detect_ash.perfil_de_dict(p)


def test_perfil_inexistente_y_toml_roto(tmp_path):
    with pytest.raises(ValueError, match="Perfiles disponibles"):
        detect_ash.carga_perfil("chile")
    roto = tmp_path / "roto.toml"
    roto.write_text("[perfil\nnombre = 1\n")
    with pytest.raises(ValueError, match="TOML"):
        detect_ash.carga_perfil(roto)


def test_el_perfil_no_se_modifica():
    p = detect_ash.carga_perfil("popocatepetl")
    with pytest.raises(AttributeError):
        p.dia_max = 60.0
    assert copy.deepcopy(p) == p


def corre(*args, cwd):
    return subprocess.run([sys.executable, str(RAIZ / "detect_ash.py"), *args],
                          cwd=cwd, capture_output=True, text=True, timeout=120)


def test_cli_perfil_en_el_geotiff(tmp_path):
    r = corre("--path", str(L2), "-m", "20190601332", "-o", f"{tmp_path}/", "--perfil", "popocatepetl", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    with rasterio.open(tmp_path / "ceniza_20190601332.tif") as f:
        etiquetas = f.tags()
    assert etiquetas["perfil"] == "popocatepetl"
    assert etiquetas["perfil_sha256"] == detect_ash.carga_perfil("popocatepetl").sha256


def test_cli_perfil_invalido(tmp_path):
    r = corre("--path", str(L2), "-m", "20190601332", "--perfil", "chile", cwd=tmp_path)
    assert r.returncode == 2
    assert "Perfiles disponibles" in r.stdout + r.stderr
