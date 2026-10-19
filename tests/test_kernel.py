"""genera_media_dst contra una implementación directa (generic_filter con nanmean/nanstd)."""
import warnings

import numpy as np
import pytest
from scipy import ndimage

from detect_ash import genera_media_dst


def referencia(a, k=5):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # ventanas sin datos
        media = ndimage.generic_filter(a, np.nanmean, size=k, mode="constant", cval=np.nan)
        dst = ndimage.generic_filter(a, np.nanstd, size=k, mode="constant", cval=np.nan)
    return media, dst


def arreglo(forma, semilla=0):
    rng = np.random.default_rng(semilla)
    a = rng.normal(0, 2, forma).astype(np.float32)
    a[rng.random(forma) < 0.1] = np.nan  # huecos dispersos
    a[:, :7] = np.nan                    # una franja sin datos, como fuera del disco
    return a


@pytest.mark.parametrize("forma", [(1, 1), (5, 5), (60, 80)])
def test_igual_a_la_referencia(forma):
    a = arreglo(forma)
    m, s = genera_media_dst(a, 5)
    mr, sr = referencia(a)
    np.testing.assert_array_equal(np.isnan(m), np.isnan(mr))
    np.testing.assert_array_equal(np.isnan(s), np.isnan(sr))
    np.testing.assert_allclose(m, mr, rtol=0, atol=1e-5, equal_nan=True)
    np.testing.assert_allclose(s, sr, rtol=0, atol=1e-5, equal_nan=True)


def test_ventana_sin_datos_da_nan():
    a = np.full((9, 9), np.nan, np.float32)
    m, s = genera_media_dst(a, 5)
    assert np.isnan(m).all() and np.isnan(s).all()
