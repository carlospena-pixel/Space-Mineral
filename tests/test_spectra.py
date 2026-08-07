"""Pruebas del grafico comparativo de firmas espectrales.

No necesitan la escena: todas las firmas son sinteticas. El backend "Agg" se
fija antes de importar pyplot para que corran sin display (CI incluido).
"""

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from matplotlib.axes import Axes  # noqa: E402

from mineralmap.config import BAND_ORDER, band_wavelengths  # noqa: E402
from mineralmap.visualization.spectra import (  # noqa: E402
    normalize_signature,
    plot_spectra,
)

# Tres bandas consecutivas en el sensor: la firma se dibuja de un solo trazo,
# asi los tests que miran los datos del eje no tienen que reensamblar tramos.
BANDAS_CONTIGUAS = ["B2", "B3", "B4"]


def _ydata(ax) -> np.ndarray:
    """Concatena los valores en y de todas las lineas dibujadas en el eje."""
    return np.concatenate([linea.get_ydata() for linea in ax.lines])


def test_devuelve_un_axes_y_crea_la_figura_si_no_se_le_pasa_una():
    """Con ax=None la funcion se hace cargo de la figura y devuelve el eje."""
    firma = np.linspace(0.1, 0.9, len(BANDAS_CONTIGUAS))

    ax = plot_spectra({"sintetica": firma}, band_order=BANDAS_CONTIGUAS)

    assert isinstance(ax, Axes)
    assert len(ax.lines) == 1


def test_el_eje_x_es_longitud_de_onda_y_no_indice_de_banda():
    """La distancia entre bandas tiene que ser la real.

    Es la decision que hace legible la pendiente del grafico: en un eje por
    indice, el salto B8A -> B11 (745 nm) y el salto B5 -> B6 (35 nm) miden lo
    mismo, y cualquier lectura de un rasgo de absorcion queda deformada.
    """
    firma = np.linspace(0.1, 0.9, len(BANDAS_CONTIGUAS))

    ax = plot_spectra({"sintetica": firma}, band_order=BANDAS_CONTIGUAS)

    xdata = np.concatenate([linea.get_xdata() for linea in ax.lines])
    np.testing.assert_allclose(xdata, band_wavelengths(BANDAS_CONTIGUAS))


def test_rechaza_una_firma_de_largo_distinto_al_de_band_order():
    """Un vector de otro largo no es la misma firma en otras bandas: es otra
    cosa. Superponerlo compararia bandas distintas sin que nada se queje."""
    with pytest.raises(ValueError, match="band_order"):
        plot_spectra({"corta": np.array([0.1, 0.2])}, band_order=BANDAS_CONTIGUAS)


def test_normalize_l2_deja_norma_unitaria():
    """Es lo que ve el SAM: direccion del vector, no magnitud."""
    firma = np.array([0.3, 0.6, 0.9])

    ax = plot_spectra({"sintetica": firma}, band_order=BANDAS_CONTIGUAS)

    np.testing.assert_allclose(np.linalg.norm(_ydata(ax)), 1.0)


def test_normalize_none_no_toca_los_valores():
    """Para cuando interesa la magnitud absoluta, el grafico no debe reescalar."""
    firma = np.array([0.3, 0.6, 0.9])

    ax = plot_spectra(
        {"sintetica": firma}, band_order=BANDAS_CONTIGUAS, normalize="none"
    )

    np.testing.assert_allclose(_ydata(ax), firma)


def test_dos_firmas_proporcionales_quedan_superpuestas_con_l2():
    """Esta es la propiedad que hace util el grafico.

    La firma de laboratorio y el pixel real difieren en un factor de escala
    (~2.1 en esta escena) que el SAM ignora por construccion. Si el grafico no
    lo ignorara tambien, mostraria dos curvas separadas y sugeriria un
    desalineamiento que no existe.
    """
    firma = np.array([0.3, 0.6, 0.9])
    escalada = firma * 2.11

    ax = plot_spectra(
        {"laboratorio": firma, "pixel": escalada}, band_order=BANDAS_CONTIGUAS
    )

    assert len(ax.lines) == 2
    np.testing.assert_allclose(
        ax.lines[0].get_ydata(), ax.lines[1].get_ydata(), rtol=1e-12
    )


def test_hay_hueco_donde_el_sensor_no_muestreo():
    """B10 no existe en L2A: entre B9 (945 nm) y B11 (1610 nm) no se traza recta.

    Unirlas continuo dibujaria una interpolacion a lo largo de 665 nm sin ni
    una medicion detras. El corte se materializa como dos lineas en vez de una.
    """
    firma = np.linspace(0.1, 0.9, len(BAND_ORDER))

    ax = plot_spectra({"sintetica": firma})

    assert len(ax.lines) == 2
    # El corte cae exactamente donde termina B9 y empieza B11.
    np.testing.assert_allclose(ax.lines[0].get_xdata()[-1], band_wavelengths(["B9"])[0])
    np.testing.assert_allclose(ax.lines[1].get_xdata()[0], band_wavelengths(["B11"])[0])
    # Una sola entrada de leyenda por firma, no una por tramo.
    assert [texto.get_text() for texto in ax.get_legend().get_texts()] == ["sintetica"]


def test_los_nan_se_propagan_en_vez_de_volverse_cero():
    """Un NaN es 'esta banda no se midio'. Convertirlo en 0 lo transforma en
    'esta banda midio cero', que es un dato distinto y ademas mueve el factor
    de normalizacion."""
    firma = np.array([0.3, np.nan, 0.9])

    normalizada = normalize_signature(firma, "l2")

    assert np.isnan(normalizada[1])
    # El factor se calcula solo sobre los finitos, asi que el NaN no arrastra
    # toda la firma.
    assert np.isfinite(normalizada[0])
    np.testing.assert_allclose(
        np.linalg.norm(normalizada[np.isfinite(normalizada)]), 1.0
    )


def test_normalizacion_desconocida_y_firma_nula_son_errores():
    """Un modo mal escrito no debe caer en un default silencioso, y un vector
    de ceros no tiene direccion que normalizar (el SAM tampoco podria)."""
    with pytest.raises(ValueError, match="no es valido"):
        normalize_signature(np.array([0.1, 0.2]), "L2")

    with pytest.raises(ValueError, match="no se puede normalizar|No se puede"):
        normalize_signature(np.zeros(3), "l2")
