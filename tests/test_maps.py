"""Pruebas del realce por percentiles, del compuesto RGB y de la figura de SCL.

Sin dependencia de la escena: el Scene y la banda SCL se arman sinteticos. El
backend "Agg" se fija antes de importar pyplot para que corran sin display (CI
incluido).
"""

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from affine import Affine  # noqa: E402
from rasterio.crs import CRS  # noqa: E402

from mineralmap.io.raster_io import Scene  # noqa: E402
from mineralmap.visualization.maps import (  # noqa: E402
    SCL_COLORS,
    percentile_stretch,
    plot_scl_classes,
    rgb_composite,
    scl_to_rgb,
)


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


def test_el_color_de_una_clase_no_depende_de_las_otras_clases_presentes():
    """Es la razon de colorear a mano en vez de dejarle un colormap a imshow.

    Un colormap se escala a los valores presentes en el recorte: el suelo
    desnudo saldria de un color en un AOI despejado y de otro en uno con nubes,
    mientras la leyenda sigue diciendo que es el mismo.
    """
    solo_suelo = np.full((2, 2), 5)
    suelo_y_nube = np.array([[5, 9], [5, 9]])

    np.testing.assert_array_equal(
        scl_to_rgb(solo_suelo)[0, 0], scl_to_rgb(suelo_y_nube)[0, 0]
    )
    assert not np.array_equal(
        scl_to_rgb(suelo_y_nube)[0, 0], scl_to_rgb(suelo_y_nube)[0, 1]
    )


def test_un_codigo_scl_fuera_de_la_tabla_se_pinta_aparte_en_vez_de_reventar():
    """Un producto con codigos inesperados hay que poder mirarlo.

    El color de reserva no puede coincidir con el de ninguna clase declarada:
    si coincidiera, la figura mostraria nieve donde hay un codigo que nadie
    sabe leer.
    """
    desconocido = scl_to_rgb(np.array([[99]]))

    assert desconocido.shape == (1, 1, 3)
    declarados = [scl_to_rgb(np.full((1, 1), codigo))[0, 0] for codigo in SCL_COLORS]
    assert not any(np.allclose(desconocido[0, 0], color) for color in declarados)


def test_la_leyenda_solo_nombra_las_clases_que_estan_en_el_recorte():
    """Listar las 12 clases sugiere que las ausentes estan presentes en
    cantidad despreciable, y no es eso: no estan."""
    scl = np.array([[5, 5], [5, 6]])
    mask = np.array([[True, True], [True, False]])

    ax_scl, _ax_mask = plot_scl_classes(scl, mask)

    etiquetas = [texto.get_text() for texto in ax_scl.get_legend().get_texts()]
    assert len(etiquetas) == 2
    assert any("suelo_desnudo" in etiqueta for etiqueta in etiquetas)
    assert any("agua" in etiqueta for etiqueta in etiquetas)
    # La clase mas abundante encabeza la leyenda, como en el resumen de la CLI.
    assert "suelo_desnudo" in etiquetas[0]


def test_la_mascara_se_dibuja_con_escala_fija_de_cero_a_uno():
    """Sin vmin/vmax, `imshow` escala al contenido y una mascara enteramente
    valida --el caso normal en este AOI-- se dibuja negra, que es justo lo
    contrario de lo que significa."""
    scl = np.full((3, 3), 5)
    mask = np.ones((3, 3), dtype=bool)

    _ax_scl, ax_mask = plot_scl_classes(scl, mask)

    assert ax_mask.images[0].get_clim() == (0.0, 1.0)


def test_el_titulo_de_la_mascara_reporta_validos_y_descartados():
    """El conteo absoluto acompana al porcentaje porque sobre 4 millones de
    pixeles un 99,9977 % son 92 pixeles descartados, y 92 se puede ir a mirar."""
    scl = np.array([[5, 5], [5, 9]])
    mask = np.array([[True, True], [True, False]])

    _ax_scl, ax_mask = plot_scl_classes(scl, mask)

    titulo = ax_mask.get_title()
    assert "75.0000 %" in titulo
    assert "1 px descartados" in titulo


def test_dibujar_un_scl_y_una_mascara_de_formas_distintas_es_un_error():
    """Son dos ventanas distintas del tile; la figura saldria perfecta y la
    comparacion entre paneles no significaria nada."""
    with pytest.raises(ValueError, match="misma forma"):
        plot_scl_classes(np.zeros((2, 2), dtype=int), np.ones((3, 3), dtype=bool))
