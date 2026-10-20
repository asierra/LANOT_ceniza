"""Ángulo cenital solar (P6) contra el cálculo topocéntrico completo de Skyfield."""
import datetime

import numpy as np
import pytest
from skyfield.api import utc, wgs84

import detect_ash

PUNTOS = [(19.02, -98.62), (22.4, -102.4), (17.5, -96.3), (40.0, -100.0), (5.0, -80.0), (-30.0, -60.0)]


@pytest.fixture(scope="module")
def efemerides():
    return detect_ash.carga_efemerides()


@pytest.mark.parametrize("fecha", [
    datetime.datetime(2019, 3, 1, 13, 0, tzinfo=utc),
    datetime.datetime(2024, 2, 27, 12, 30, tzinfo=utc),
    datetime.datetime(2026, 6, 21, 12, 30, tzinfo=utc),
    datetime.datetime(2026, 10, 19, 0, 30, tzinfo=utc),
])
def test_sza_contra_skyfield(efemerides, fecha):
    eph, ts = efemerides
    lat = np.array([p[0] for p in PUNTOS])
    lon = np.array([p[1] for p in PUNTOS])
    sza = detect_ash.get_sun_zenith_angle(lat, lon, fecha, eph, ts)
    t = ts.from_datetime(fecha)
    ref = [90 - (eph["earth"] + wgs84.latlon(la, lo)).at(t).observe(eph["sun"]).apparent().altaz()[0].degrees
           for la, lo in PUNTOS]
    np.testing.assert_allclose(sza, ref, atol=0.01)  # antes del 2026-10 el error era de 0.2-0.4°
