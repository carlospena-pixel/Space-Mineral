"""Pruebas del realce por percentiles y del compuesto RGB.

Sin dependencia de la escena: el Scene se arma sintetico.
"""

import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from mineralmap.io.raster_io import Scene
from mineralmap.visualization.maps import percentile_stretch, rgb_composite


def _scene_sintetico(cube: np.ndarray) -> Scene:
    """Scene minimo de 3 bandas B2/B3/B4 sobre el cubo dado."""
    alto, ancho = cube.shape[1:]
    return Scene(
        cube=cube,
        band_names=["B2", "B3", "B4"],
        transform=Affine.identity(),
        crs=CRS.from_epsg(32719),
        mask=np.ones((alto, ancho), dtype=bool),
    )


def test_el_realce_lleva_el_rango_util_a_cero_uno():
    """El recorte por percentiles satura las colas y estira el resto a [0,1]."""
    banda = np.linspace(0.2, 0.4, 101).reshape(101, 1)

    realzada = percentile_stretch(banda)

    assert realzada.min() == 0.0
    assert realzada.max() == 1.0
    assert realzada.shape == banda.shape


def test_el_realce_ignora_los_nan_en_vez_de_contagiarlos():
    """Un cubo ya enmascarado tiene NaN, y con np.percentile un solo NaN
    devuelve NaN como percentil y deja la imagen entera negra sin lanzar nada.
    Los NaN se preservan, pero no contaminan el calculo del rango."""
    banda = np.linspace(0.2, 0.4, 100).reshape(10, 10)
    banda[0, 0] = np.nan

    realzada = percentile_stretch(banda)

    assert np.isnan(realzada[0, 0])
    finitos = realzada[np.isfinite(realzada)]
    assert finitos.min() == 0.0
    assert finitos.max() == 1.0


def test_una_banda_constante_o_vacia_no_revienta():
    """Sin contraste no hay nada que estirar; devolver ceros es preferible a
    dividir por cero."""
    np.testing.assert_array_equal(percentile_stretch(np.full((3, 3), 0.5)), 0.0)
    np.testing.assert_array_equal(percentile_stretch(np.full((3, 3), np.nan)), 0.0)


def test_el_compuesto_apila_las_bandas_en_el_orden_pedido():
    """R, G, B se buscan por nombre; el orden del cubo no manda aca.

    Es la unica capa del proyecto que busca bandas por nombre: un compuesto en
    color tiene que saber cual banda es el rojo, mientras el resto del pipeline
    trabaja posicionalmente.
    """
    cube = np.stack(
        [
            np.full((4, 4), 0.1),  # B2
            np.linspace(0.0, 1.0, 16).reshape(4, 4),  # B3
            np.full((4, 4), 0.9),  # B4
        ]
    )
    scene = _scene_sintetico(cube)

    rgb = rgb_composite(scene, bands=("B4", "B3", "B2"))

    assert rgb.shape == (4, 4, 3)
    # B3 es la unica con contraste, y quedo en el canal verde.
    assert rgb[..., 1].max() == 1.0
    assert rgb[..., 0].max() == 0.0
    assert rgb[..., 2].max() == 0.0


def test_pedir_una_banda_que_el_scene_no_trae_es_un_error():
    """Sin esto, un Scene armado con COMMON_BANDS daria un IndexError opaco."""
    scene = _scene_sintetico(np.zeros((3, 2, 2)))

    with pytest.raises(ValueError, match="B11"):
        rgb_composite(scene, bands=("B11", "B3", "B2"))
