"""Rutas configurables (P3)."""
import detect_ash


def test_variable_de_entorno_manda(monkeypatch, tmp_path):
    monkeypatch.setenv("LANOT_SKYFIELD_DIR", str(tmp_path))
    assert detect_ash.carpeta_skyfield() == tmp_path


def test_carpeta_de_lanot_si_tiene_el_archivo(monkeypatch, tmp_path):
    monkeypatch.delenv("LANOT_SKYFIELD_DIR", raising=False)
    (tmp_path / "de421.bsp").touch()
    monkeypatch.setattr(detect_ash, "SKYFIELD_LANOT", tmp_path)
    assert detect_ash.carpeta_skyfield() == tmp_path


def test_cache_de_usuario_fuera_de_lanot(monkeypatch, tmp_path):
    monkeypatch.delenv("LANOT_SKYFIELD_DIR", raising=False)
    monkeypatch.setattr(detect_ash, "SKYFIELD_LANOT", tmp_path / "no_existe")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert detect_ash.carpeta_skyfield() == tmp_path / "cache" / "lanot_ceniza"
    assert not (tmp_path / "no_existe").exists()  # no intenta crear la carpeta del sistema
