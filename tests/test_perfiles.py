"""Perfiles de umbrales (perfiles/*.toml).

- Cada perfil tiene la estructura esperada: ni claves de más ni de menos.
- El del Popocatépetl describe exactamente lo que hace classify_ash: un clasificador de
  referencia que solo lee el perfil debe dar los mismos píxeles en arreglos sintéticos
  que cubren los tres bloques, el kernel, las seis fases y los valores en el límite.

Mientras classify_ash no lea el perfil (ver doc/2026-10-21_perfiles_umbrales.md), esta
prueba es la que impide que el archivo y el código digan cosas distintas.
"""
import tomllib
from pathlib import Path

import numpy as np
import pytest

import detect_ash

PERFILES = Path(__file__).parents[1] / "perfiles"
CLASES = {"sin_ceniza": 0, "ca": 1, "hap": 2, "lap": 3}
FASES = {"despejado": 0, "agua": 1, "superenfriada": 2, "mixta": 3, "hielo": 4, "desconocida": 5}
BLOQUES = ("noche", "crepusculo", "dia")


def lee(nombre):
    with open(PERFILES / f"{nombre}.toml", "rb") as f:
        return tomllib.load(f)


def claves(d, obligatorias, opcionales=(), donde=""):
    faltan = set(obligatorias) - set(d)
    sobran = set(d) - set(obligatorias) - set(opcionales)
    assert not faltan, f"{donde}: faltan {sorted(faltan)}"
    assert not sobran, f"{donde}: claves desconocidas {sorted(sobran)}"


def valida(p):
    """Validación estricta. La versión definitiva irá en detect_ash al leer el perfil."""
    claves(p, ["perfil", "iluminacion", "kernel", *BLOQUES, "refinamiento_hap", "filtro_dt3",
               "fase", "region"], donde="raíz")
    claves(p["perfil"], ["nombre", "descripcion", "estado"], donde="perfil")
    assert p["perfil"]["estado"] in ("operacion", "ejemplo")

    il = p["iluminacion"]
    claves(il, ["dia_max", "noche_min"], donde="iluminacion")
    assert 0 < il["dia_max"] < il["noche_min"] < 180

    k = p["kernel"]
    claves(k, ["tamano", "umbral", "ca_dt1_max", "hap_dt1_max"], donde="kernel")
    assert isinstance(k["tamano"], int) and k["tamano"] >= 3 and k["tamano"] % 2 == 1

    for b in BLOQUES:
        claves(p[b], ["ca", "hap"], donde=b)
        for c in ("ca", "hap"):
            prueba = p[b][c]
            claves(prueba, ["dt1_max", "dt2_min", "dt3_min"], ["r137_min", "bt13_max"], donde=f"{b}.{c}")
            assert all(isinstance(v, float) for v in prueba.values()), f"{b}.{c}: escribir con punto decimal"

    r = p["refinamiento_hap"]
    claves(r, ["hap_dt2_min", "lap_dt2_min"], donde="refinamiento_hap")
    assert r["lap_dt2_min"] <= r["hap_dt2_min"]
    claves(p["filtro_dt3"], ["ca_hap_max", "lap_max"], donde="filtro_dt3")

    f = p["fase"]
    claves(f, ["ca", "hap", "lap", "nube"], donde="fase")
    for c in ("ca", "hap", "lap"):
        claves(f[c], FASES, donde=f"fase.{c}")
        assert set(f[c].values()) <= set(CLASES), f"fase.{c}: solo puede dar {sorted(CLASES)}"
    assert set(f["nube"]) <= set(FASES)

    reg = p["region"]
    claves(reg, ["dominio", "volcan"], ["recorte", "puntos"], donde="region")
    assert reg["dominio"] in ("C", "F")
    assert ("recorte" in reg) != ("puntos" in reg), "region: recorte o puntos, uno de los dos"
    if "recorte" in reg:
        assert reg["recorte"] in detect_ash.CLIP_REGIONS
    else:
        pts = reg["puntos"]
        assert len(pts) >= 2
        assert all(len(q) == 2 and -180 <= q[0] <= 180 and -90 <= q[1] <= 90 for q in pts), "puntos: [lon, lat]"
        assert dentro(reg["volcan"]["lon"], reg["volcan"]["lat"], pts), "el volcán queda fuera de la región"


def dentro(lon, lat, pts):
    """Punto en rectángulo (2 puntos) o en polígono (3 o más; regla de par e impar)."""
    if len(pts) == 2:
        (x0, y0), (x1, y1) = pts
        return min(x0, x1) <= lon <= max(x0, x1) and min(y0, y1) <= lat <= max(y0, y1)
    adentro = False
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        if (y0 > lat) != (y1 > lat) and lon < x0 + (lat - y0) * (x1 - x0) / (y1 - y0):
            adentro = not adentro
    return adentro


def clasifica_con_perfil(p, c04, c07, c11, c13, c15, phase, sza, valid_data_mask):
    """Clasificador de referencia: misma estructura que classify_ash, números del perfil."""
    d1, d2, d3 = c13 - c15, c11 - c13, c07 - c13
    il, k = p["iluminacion"], p["kernel"]

    media, dst = detect_ash.genera_media_dst(d1, kernel_size=k["tamano"])
    textura = d1 - media * dst < k["umbral"]
    kernel_ca = textura & (d1 < k["ca_dt1_max"])
    kernel_hap = textura & (d1 < k["hap_dt1_max"]) & ~kernel_ca

    def cumple(u):
        m = (d1 < u["dt1_max"]) & (d2 > u["dt2_min"]) & (d3 > u["dt3_min"])
        if "r137_min" in u:
            m &= c04 > u["r137_min"]
        if "bt13_max" in u:
            m &= c13 < u["bt13_max"]
        return m

    def bloque(b):
        ca = cumple(p[b]["ca"]) | kernel_ca
        hap = cumple(p[b]["hap"]) | kernel_hap
        return np.where(ca, 1, np.where(hap, 2, 0))

    clase = np.select(
        [sza > il["noche_min"], (sza >= il["dia_max"]) & (sza <= il["noche_min"]), sza < il["dia_max"]],
        [bloque("noche"), bloque("crepusculo"), bloque("dia")], default=0)

    r = p["refinamiento_hap"]
    hap = clase == 2
    clase = np.where(hap & (d2 >= r["hap_dt2_min"]), 2,
                     np.where(hap & (d2 >= r["lap_dt2_min"]), 3,
                              np.where(hap & (d2 < r["lap_dt2_min"]), 0, clase)))

    f = p["filtro_dt3"]
    clase = np.where((clase <= 2) & (d3 <= f["ca_hap_max"]), 0,
                     np.where((clase >= 3) & (d3 <= f["lap_max"]), 0, clase))

    salida = clase.copy()
    for nombre in ("ca", "hap", "lap"):
        for fase, resultado in p["fase"][nombre].items():
            salida[(clase == CLASES[nombre]) & (phase == FASES[fase])] = CLASES[resultado]

    salida = salida.astype(np.uint8)
    salida[(salida == 0) & np.isin(phase, [FASES[x] for x in p["fase"]["nube"]])] = detect_ash.NUBE
    salida[~valid_data_mask] = detect_ash.SIN_DATOS
    return salida


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
def test_estructura(nombre):
    p = lee(nombre)
    valida(p)
    assert p["perfil"]["nombre"] == nombre


@pytest.mark.parametrize("semilla,malla", [(1, True), (2, True), (3, False)])
def test_popocatepetl_es_el_codigo(semilla, malla):
    p = lee("popocatepetl")
    datos = escena(semilla, malla=malla)
    esperado = detect_ash.classify_ash(**datos, kernel_size=p["kernel"]["tamano"])
    obtenido = clasifica_con_perfil(p, **datos)
    distintos = int((esperado != obtenido).sum())
    assert distintos == 0, f"{distintos} píxeles distintos entre el perfil y classify_ash"
    # que la escena ejercite todas las salidas
    assert set(np.unique(esperado)) == {0, 1, 2, 3, 6, 255}


def test_popocatepetl_nube_y_region():
    p = lee("popocatepetl")
    assert tuple(FASES[x] for x in p["fase"]["nube"]) == detect_ash.FASES_NUBE
    assert p["region"]["recorte"] == "ashpaper"


def test_la_prueba_detecta_un_cambio():
    """Si el perfil dice otra cosa, la comparación lo nota."""
    p = lee("popocatepetl")
    p["dia"]["hap"]["r137_min"] = 0.003
    datos = escena(1)
    assert (detect_ash.classify_ash(**datos) != clasifica_con_perfil(p, **datos)).any()
