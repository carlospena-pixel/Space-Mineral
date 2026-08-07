"""Pruebas de get_reference_spectrum: firma de referencia alineada a BAND_ORDER."""

import numpy as np
import pytest

from mineralmap.config import BAND_ORDER, SAM_BANDS, band_wavelengths
from mineralmap.spectral.endmembers import (
    _RAW_BAND_ORDER,
    DEFAULT_WAVELENGTH_TOLERANCE_NM,
    USGS_RESAMPLING_PLATFORM,
    find_usgs_wavelengths_file,
    get_reference_spectrum,
    validate_raw_band_order,
)
from mineralmap.spectral.usgs_library import load_usgs_wavelengths


def test_kaolinite_devuelve_12_bandas_sin_b10():
    """La firma debe tener 12 valores (se descarta B10, que no existe en L2A)."""
    firma = get_reference_spectrum("kaolinite")

    assert firma.shape == (len(BAND_ORDER),)
    assert "B10" not in BAND_ORDER
    assert np.all(np.isfinite(firma))


def test_kaolinite_absorcion_al_oh_en_b12():
    """La caolinita cae fuerte en B12 (~2.2 um) por la absorcion Al-OH:
    B12 debe ser bastante menor que B11."""
    firma = get_reference_spectrum("kaolinite")
    b11 = firma[BAND_ORDER.index("B11")]
    b12 = firma[BAND_ORDER.index("B12")]

    assert b12 < b11


def test_firma_pedida_en_otro_orden_conserva_el_valor_de_cada_banda():
    """Cambiar `band_order` reordena la firma, no la reasigna.

    Este es el punto de fallo silencioso mas caro del proyecto. Cuando el
    detector pase a consumir SAM_BANDS, va a subconjuntar el cubo por indice y
    a pedir la firma con el mismo `band_order`; si la reordenacion se hiciera
    mal, `get_reference_spectrum` seguiria devolviendo 9 numeros del rango
    correcto y el SAM seguiria calculando un angulo. Nada fallaria: el mapa
    saldria equivocado y con buena pinta. El test ata cada valor a su banda.
    """
    por_defecto = get_reference_spectrum("kaolinite", band_order=BAND_ORDER)
    subconjunto = get_reference_spectrum("kaolinite", band_order=SAM_BANDS)

    assert subconjunto.shape == (len(SAM_BANDS),)
    for posicion, banda in enumerate(SAM_BANDS):
        mensaje = f"{banda} cambio de valor al pedir la firma en otro orden"
        assert subconjunto[posicion] == por_defecto[BAND_ORDER.index(banda)], mensaje


def test_firma_pedida_al_reves_queda_al_reves():
    """Si se pide el orden invertido, la firma sale invertida; nada la reordena
    por su cuenta. Es el complemento del test anterior: comprueba que el orden
    lo fija el llamador y no una convencion escondida en la funcion."""
    directa = get_reference_spectrum("kaolinite", band_order=BAND_ORDER)
    invertida = get_reference_spectrum("kaolinite", band_order=BAND_ORDER[::-1])

    np.testing.assert_allclose(invertida, directa[::-1])


def test_raw_band_order_esta_en_orden_creciente_de_longitud_de_onda():
    """Las 13 posiciones del archivo USGS avanzan hacia el infrarrojo.

    No necesita el archivo de longitudes de onda: compara `_RAW_BAND_ORDER`
    contra la tabla del proyecto. Es la mitad de la validacion que si se puede
    correr en una copia limpia del repositorio.
    """
    assert validate_raw_band_order() is None

    lambdas = band_wavelengths(_RAW_BAND_ORDER, platform=USGS_RESAMPLING_PLATFORM)
    assert lambdas == sorted(lambdas)
    assert len(_RAW_BAND_ORDER) == 13
    assert "B10" in _RAW_BAND_ORDER


def test_validate_raw_band_order_denuncia_un_archivo_desordenado():
    """Un vector de longitudes de onda no creciente es un archivo en otro orden.

    Se prueba con datos sinteticos porque es justo el caso que no se puede
    reproducir con el archivo real: si el archivo estuviera desordenado, el
    proyecto entero llevaria meses calculando sobre bandas cruzadas.
    """
    correctas = np.array(
        band_wavelengths(_RAW_BAND_ORDER, platform=USGS_RESAMPLING_PLATFORM)
    )

    # Sin tocar nada, el vector correcto pasa y no se desvia de si mismo.
    desvios = validate_raw_band_order(correctas)
    np.testing.assert_allclose(desvios, 0.0)

    desordenadas = correctas.copy()
    desordenadas[[10, 11]] = desordenadas[[11, 10]]
    with pytest.raises(ValueError, match="crecientes"):
        validate_raw_band_order(desordenadas)

    with pytest.raises(ValueError, match="13 longitudes de onda"):
        validate_raw_band_order(correctas[:5])


def test_validate_raw_band_order_denuncia_un_desvio_fuera_de_tolerancia():
    """Un corrimiento mayor que la tolerancia tiene que fallar, no redondearse."""
    corridas = np.array(
        band_wavelengths(_RAW_BAND_ORDER, platform=USGS_RESAMPLING_PLATFORM)
    )
    corridas[-1] += DEFAULT_WAVELENGTH_TOLERANCE_NM + 1.0

    with pytest.raises(ValueError, match="B12"):
        validate_raw_band_order(corridas)


@pytest.mark.skipif(
    find_usgs_wavelengths_file() is None,
    reason=(
        "requiere el archivo de longitudes de onda de splib07 en "
        "data/external/ (ver find_usgs_wavelengths_file)"
    ),
)
def test_longitudes_de_onda_del_archivo_usgs_calzan_con_la_tabla_de_esa():
    """Ancla `_RAW_BAND_ORDER` a la fuente y no solo a la evidencia fisica.

    Hasta ahora el orden de las 13 posiciones se justificaba por la forma de la
    firma (la caida aislada de la posicion 10 solo puede ser el sobretono OH de
    ~1400 nm que muestrea B10). Este test lo ata al dato: cada posicion del
    archivo declara su longitud de onda y tiene que caer sobre la banda que
    `_RAW_BAND_ORDER` le asigna.
    """
    ruta = find_usgs_wavelengths_file()
    lambdas_usgs = load_usgs_wavelengths(str(ruta))

    desvios = validate_raw_band_order(lambdas_usgs)

    assert desvios is not None
    assert desvios.max() <= DEFAULT_WAVELENGTH_TOLERANCE_NM
