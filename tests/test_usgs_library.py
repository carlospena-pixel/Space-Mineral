"""Pruebas del parser de la libreria espectral USGS splib07 (rsSentinel2)."""

import numpy as np
import pytest

from mineralmap.spectral.usgs_library import load_usgs_rs_sentinel2


def _escribir_archivo_usgs(path, valores):
    """Crea un archivo USGS sintetico: 1 linea de encabezado + un valor por linea."""
    lineas = ["S07SNTL2 Record=1: MINERAL DE PRUEBA"]
    lineas += [f" {v:.7e}" for v in valores]
    path.write_text("\n".join(lineas), encoding="utf-8")


def test_lee_13_valores_en_orden(tmp_path):
    """El parser salta el encabezado y devuelve los 13 valores en orden."""
    valores = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60,
               0.70, 0.80, 0.85, 0.90, 0.15, 0.79, 0.40]
    archivo = tmp_path / "mineral.txt"
    _escribir_archivo_usgs(archivo, valores)

    firma = load_usgs_rs_sentinel2(str(archivo))

    assert firma.shape == (13,)
    np.testing.assert_allclose(firma, valores)


def test_convierte_nodata_a_nan(tmp_path):
    """Los valores 'no dato' (muy negativos, p. ej. -1.23e34) pasan a NaN."""
    valores = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60,
               0.70, 0.80, 0.85, 0.90, -1.23e34, 0.79, 0.40]
    archivo = tmp_path / "mineral_nodata.txt"
    _escribir_archivo_usgs(archivo, valores)

    firma = load_usgs_rs_sentinel2(str(archivo))

    assert np.isnan(firma[10])        # el 'no dato' se convirtio en NaN
    assert np.isfinite(firma[0])      # los demas valores quedan intactos
    np.testing.assert_allclose(firma[11], 0.79)


def test_archivo_incompleto_lanza_error(tmp_path):
    """Si el archivo trae menos de 13 valores, debe fallar con ValueError."""
    archivo = tmp_path / "corto.txt"
    _escribir_archivo_usgs(archivo, [0.1, 0.2, 0.3])

    with pytest.raises(ValueError):
        load_usgs_rs_sentinel2(str(archivo))
