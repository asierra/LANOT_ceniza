"""Búsqueda de archivos L2 por instante (P2): nombres reales de distintas épocas, duplicados
y archivos que se parecen pero no son los que necesita el algoritmo."""
import pytest

from detect_ash import PRODUCTOS, busca_archivos

BANDAS = [p for p in PRODUCTOS if p.startswith("C")]


def nombres(origen="OR", modo=6, sat="G16", inst="20240580406", seg="173", c="20240580409000", dom="C"):
    s = f"s{inst}{seg}"
    e = f"e{inst[:7]}9999999"
    out = [f"{origen}_ABI-L2-ACTP{dom}-M{modo}_{sat}_{s}_{e}_c{c}.nc"]
    out += [f"{origen}_ABI-L2-CMIP{dom}-M{modo}{b}_{sat}_{s}_{e}_c{c}.nc" for b in BANDAS]
    return out


def carpeta(tmp_path, *listas):
    for lista in listas:
        for n in lista:
            (tmp_path / n).touch()
    return tmp_path


def test_completo_m6(tmp_path):
    d = carpeta(tmp_path, nombres())
    encontrados, faltan = busca_archivos(d, "20240580406")
    assert not faltan
    assert set(encontrados) == set(PRODUCTOS)
    assert encontrados["C07"].name.startswith("OR_ABI-L2-CMIPC-M6C07_G16_")
    assert "ACTPC" in encontrados["ACTP"].name


def test_completo_m3_goes19_y_disco_completo(tmp_path):
    carpeta(tmp_path, nombres(modo=3, inst="20190601332", seg="133"))
    assert not busca_archivos(tmp_path, "20190601332")[1]
    otra = tmp_path / "g19"; otra.mkdir()
    carpeta(otra, nombres(sat="G19", inst="20262922216", seg="177", dom="F"))
    assert not busca_archivos(otra, "20262922216")[1]


def test_prefiere_cg_sobre_or(tmp_path):
    carpeta(tmp_path, nombres(origen="OR", modo=3, inst="20190601332"), nombres(origen="CG", modo=3, inst="20190601332"))
    encontrados, _ = busca_archivos(tmp_path, "20190601332")
    assert all(f.name.startswith("CG_") for f in encontrados.values())


def test_entre_duplicados_del_mismo_origen_el_mas_reciente(tmp_path):
    carpeta(tmp_path, nombres(c="20240580409000"), nombres(c="20240581200000"))
    encontrados, _ = busca_archivos(tmp_path, "20240580406")
    assert all("_c20240581200000" in f.name for f in encontrados.values())


def test_ignora_l1b_multibanda_y_mesoescala(tmp_path):
    inst, s = "20240580406", "s20240580406173_e20240580408546_c20240580409000.nc"
    trampas = [f"OR_ABI-L1b-RadC-M6C04_G16_{s}", f"OR_ABI-L2-MCMIPC-M6_G16_{s}",
               f"OR_ABI-L2-CMIPM1-M6C07_G16_{s}", f"OR_ABI-L2-ACHAC-M6_G16_{s}"]
    carpeta(tmp_path, nombres(), trampas)
    encontrados, faltan = busca_archivos(tmp_path, inst)
    assert not faltan
    assert not any(f.name in trampas for f in encontrados.values())


def test_solo_trampas_no_cuenta_como_completo(tmp_path):
    s = "s20240580406173_e20240580408546_c20240580409000.nc"
    carpeta(tmp_path, [f"OR_ABI-L1b-RadC-M6{b}_G16_{s}" for b in BANDAS])
    encontrados, faltan = busca_archivos(tmp_path, "20240580406")
    assert set(faltan) == set(PRODUCTOS)


def test_reporta_lo_que_falta(tmp_path):
    carpeta(tmp_path, [n for n in nombres() if "M6C11_" not in n and "ACTPC" not in n])
    _, faltan = busca_archivos(tmp_path, "20240580406")
    assert sorted(faltan) == ["ACTP", "C11"]


def test_no_mezcla_satelites(tmp_path):
    # Un juego completo de G19 y una banda suelta de G18: se usa el de G19.
    carpeta(tmp_path, nombres(sat="G19"), [nombres(sat="G18", dom="P")[1]])
    encontrados, faltan = busca_archivos(tmp_path, "20240580406")
    assert not faltan and all("_G19_" in f.name for f in encontrados.values())


def test_dos_juegos_completos_es_ambiguo(tmp_path):
    carpeta(tmp_path, nombres(sat="G16"), nombres(sat="G19"))
    with pytest.raises(ValueError, match="G16.*G19|G19.*G16"):
        busca_archivos(tmp_path, "20240580406")


def test_carpeta_inexistente(tmp_path):
    encontrados, faltan = busca_archivos(tmp_path / "no_existe", "20240580406")
    assert not encontrados and set(faltan) == set(PRODUCTOS)
