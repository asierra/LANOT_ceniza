"""Reglas de classify_ash, una prueba por regla.

Documentan el comportamiento actual (ciencia de mayo de 2026, 9dd4752). Las pruebas
marcadas con "cambia en P#" fijan reglas que el plan doc/2026-10-19_plan_mejoras_operacion.md
propone cambiar; se actualizan en el mismo commit que haga el cambio.

Los píxeles se arman a partir de los deltas: ΔT1 = C13 − C15, ΔT2 = C11 − C13, ΔT3 = C07 − C13.
"""
import numpy as np
import pytest

from detect_ash import classify_ash

NOCHE, CREPUSCULO, DIA = 100.0, 80.0, 50.0
SIN_FASE = 0  # ACTP: 0 despejado, 1 agua líquida, 2 superenfriada, 3 mixta, 4 hielo, 5 desconocida


def pixel(d1, d2, d3, sza, c04=0.01, c13=250.0, fase=SIN_FASE, valido=True):
    """Clasifica un solo píxel (arreglos de 1×1). Con un solo píxel el kernel no actúa
    salvo que ΔT1 < −1, porque la desviación local es 0."""
    a = lambda v: np.array([[v]], dtype=np.float32)
    c = classify_ash(c04=a(c04), c07=a(c13 + d3), c11=a(c13 + d2), c13=a(c13), c15=a(c13 - d1),
                     phase=a(fase), sza=a(sza), valid_data_mask=np.array([[valido]]))
    return int(c[0, 0])


def kernel(d1_centro, d2, d3, sza=NOCHE, fase=SIN_FASE):
    """5×5 en el que solo el píxel central cumple la condición del kernel: vecinos con
    ΔT1 alternando 2 y 4 (media ≈ 2.9, σ ≈ 1.1), así que ΔT1 − media·σ < −1 en el centro.
    Los vecinos no clasifican (ΔT1 ≥ 1). Devuelve la clase del centro."""
    d1 = np.where(np.indices((5, 5)).sum(axis=0) % 2 == 0, 2.0, 4.0).astype(np.float32)
    d1[2, 2] = d1_centro
    c13 = np.full((5, 5), 250.0, np.float32)
    lleno = lambda v: np.full((5, 5), v, np.float32)
    phase = lleno(SIN_FASE)
    phase[2, 2] = fase  # solo el centro, para que los vecinos sigan en 0
    c = classify_ash(c04=lleno(0.01), c07=c13 + d3, c11=c13 + d2, c13=c13, c15=c13 - d1,
                     phase=phase, sza=lleno(sza), valid_data_mask=np.ones((5, 5), bool))
    assert (np.delete(c.ravel(), 12) == 0).all(), "los vecinos no deben clasificar"
    return int(c[2, 2])


# --- Bloques por umbrales -----------------------------------------------------------

@pytest.mark.parametrize("sza", [NOCHE, CREPUSCULO, DIA])
def test_ceniza_confirmada(sza):
    assert pixel(-0.5, 0.5, 3, sza) == 1


@pytest.mark.parametrize("sza", [NOCHE, CREPUSCULO, DIA])
def test_probabilidad_alta(sza):
    assert pixel(0.5, -0.2, 3, sza) == 2


@pytest.mark.parametrize("d1,d2,d3", [(1.5, 0.5, 3), (-0.5, -0.7, 3), (-0.5, 0.5, 1.5)])
def test_sin_ceniza(d1, d2, d3):
    assert pixel(d1, d2, d3, NOCHE) == 0


def test_noche_no_usa_c04_ni_c13():
    assert pixel(0.5, -0.2, 3, NOCHE, c04=0.0, c13=290) == 2


def test_crepusculo_hap_exige_c04_y_c13_frio():
    assert pixel(0.5, -0.2, 3, CREPUSCULO, c04=0.001) == 0
    assert pixel(0.5, -0.2, 3, CREPUSCULO, c13=280) == 0


def test_crepusculo_ca_no_exige_c04():
    assert pixel(-0.5, 0.5, 3, CREPUSCULO, c04=0.0) == 1


def test_dia_exige_c04():
    # Desde mayo (9dd4752) también la ceniza confirmada; en diciembre no.
    assert pixel(-0.5, 0.5, 3, DIA, c04=0.001) == 0
    assert pixel(0.5, -0.2, 3, DIA, c04=0.001) == 0


def test_dia_no_exige_c13_frio():
    assert pixel(0.5, -0.2, 3, DIA, c13=280) == 2


@pytest.mark.parametrize("sza", [70.0, 85.0])
def test_limites_del_crepusculo(sza):
    # 70 ≤ SZA ≤ 85 es crepúsculo (P8): la CA no exige C04, el HAP exige C13 frío.
    assert pixel(-0.5, 0.5, 3, sza, c04=0.0) == 1
    assert pixel(0.5, -0.2, 3, sza, c13=280) == 0


def test_justo_fuera_del_crepusculo():
    assert pixel(0.5, -0.2, 3, 85.001, c13=280, c04=0.0) == 2   # noche
    assert pixel(-0.5, 0.5, 3, 69.999, c04=0.0) == 0             # día, exige C04


def test_sin_datos():
    assert pixel(-0.5, 0.5, 3, NOCHE, valido=False) == 255


# --- Kernel estadístico ---------------------------------------------------------------

def test_kernel_ceniza_confirmada():
    # ΔT2 < 0 no cumple el umbral de CA; solo el kernel la recupera.
    assert kernel(-0.5, d2=-2.0, d3=3) == 1


def test_kernel_probabilidad_alta():
    assert kernel(0.5, d2=-0.8, d3=3) == 2


def test_un_pixel_aislado_con_dt1_muy_negativo_es_kernel():
    # Con σ = 0, ΔT1 < −1 basta para el kernel aunque ΔT2 y ΔT3 no cumplan los umbrales.
    assert pixel(-1.5, -2.0, 3, NOCHE) == 1


# --- Filtros de ΔT2 y ΔT3 (solo alcanzables vía kernel para HAP) -------------------

def test_hap_con_dt2_entre_menos_1_y_menos_1_5_pasa_a_lap():
    assert kernel(0.5, d2=-1.2, d3=3) == 3


def test_hap_con_dt2_menor_a_menos_1_5_se_elimina():
    assert kernel(0.5, d2=-2.0, d3=3) == 0


def test_hap_con_dt3_no_positivo_se_elimina():
    assert kernel(0.5, d2=-0.8, d3=0) == 0


def test_lap_con_dt3_hasta_1_5_se_elimina():
    assert kernel(0.5, d2=-1.2, d3=1.5) == 0


def test_ca_del_kernel_con_dt3_no_positivo_se_elimina():
    # P11 (por decidir): el texto del artículo dice que la CA no se toca.
    assert kernel(-0.5, d2=-2.0, d3=0) == 0


# --- Regla de fase (P10, por decidir) -------------------------------------------------
# Lo que la regla de fase elimina queda como 6 (nube) si la fase es mixta (3) o hielo (4).

@pytest.mark.parametrize("fase,esperado", [(0, 2), (1, 3), (2, 2), (3, 2), (4, 6), (5, 2)])
def test_fase_sobre_hap(fase, esperado):
    assert pixel(0.5, -0.2, 3, NOCHE, fase=fase) == esperado


@pytest.mark.parametrize("fase,esperado", [(0, 3), (1, 0), (2, 0), (3, 6), (4, 6), (5, 0)])
def test_fase_sobre_lap(fase, esperado):
    assert kernel(0.5, d2=-1.2, d3=3, fase=fase) == esperado


# --- Nube (6) ----------------------------------------------------------------------------

@pytest.mark.parametrize("fase,esperado", [(0, 0), (1, 0), (2, 0), (3, 6), (4, 6), (5, 0)])
def test_sin_ceniza_bajo_nube(fase, esperado):
    # La fase superenfriada (2) no cuenta como nube por ahora (por revisar).
    assert pixel(1.5, 0.5, 3, NOCHE, fase=fase) == esperado


def test_nube_sin_datos_sigue_sin_datos():
    assert pixel(1.5, 0.5, 3, NOCHE, fase=4, valido=False) == 255


@pytest.mark.parametrize("fase", [0, 1, 2, 3, 4, 5])
def test_fase_no_toca_ca(fase):
    assert pixel(-0.5, 0.5, 3, NOCHE, fase=fase) == 1
