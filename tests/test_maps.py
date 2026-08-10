"""Pruebas del realce por percentiles, del compuesto RGB y de las figuras de
SCL y del mapa de puntaje.

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
    plot_score_map,
    rgb_composite,
    scl_to_rgb,
)

# Transform de un AOI plausible: origen en UTM 19S y pixel de 20 m. Los tests
# del mapa de puntaje comprueban que los ejes salgan en coordenadas del CRS, y
# con la identidad no se distinguirian de indices de pixel.
TRANSFORM_AOI = Affine(20.0, 0.0, 420000.0, 0.0, -20.0, 7780000.0)


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


def _scene_para_puntajes(alto: int = 8, ancho: int = 8) -> Scene:
    """Scene con georreferenciacion realista, para las figuras de puntaje."""
    return Scene(
        cube=np.zeros((3, alto, ancho), dtype=np.float32),
        band_names=["B2", "B3", "B4"],
        transform=TRANSFORM_AOI,
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


def test_el_mapa_de_puntaje_devuelve_los_dos_paneles():
    """Mapa e histograma son la misma pregunta mirada de dos formas: el mapa
    dice donde, el histograma dice si hay algo que mirar."""
    scene = _scene_para_puntajes()
    angulos = np.linspace(0.16, 0.45, 64).reshape(8, 8)

    ax_mapa, ax_hist = plot_score_map(angulos, scene, title="prueba")

    assert len(ax_mapa.images) == 1
    # Las barras del histograma son parches; si el panel derecho estuviera
    # vacio, el entregable de coherencia espectral no existiria.
    assert len(ax_hist.patches) > 0


def test_el_colorbar_del_mapa_declara_que_la_unidad_es_el_radian():
    """El numero que se lee en la barra es un angulo, no un puntaje en [0,1];
    sin decirlo, un 0.25 se interpreta como "25 % de parecido"."""
    scene = _scene_para_puntajes()

    ax_mapa, _ax_hist = plot_score_map(np.full((8, 8), 0.3), scene)

    assert "rad" in ax_mapa.images[0].colorbar.ax.get_ylabel()


def test_los_ejes_del_mapa_van_en_coordenadas_del_crs_y_no_en_indices():
    """Un mapa cuyo eje dice "4" no se puede cruzar con ninguna otra capa ni
    ubicar en un SIG. El extent sale de `scene.transform`."""
    scene = _scene_para_puntajes(alto=8, ancho=8)

    ax_mapa, _ax_hist = plot_score_map(np.full((8, 8), 0.3), scene)

    izq, der, abajo, arriba = ax_mapa.images[0].get_extent()
    assert (izq, arriba) == (420000.0, 7780000.0)
    # 8 px de 20 m son 160 m de lado.
    assert (der, abajo) == (420160.0, 7779840.0)


def test_un_mapa_con_nan_no_deja_los_limites_del_color_en_nan():
    """Con `np.percentile`, un solo NaN devuelve NaN como limite: `imshow` no
    lanza nada y dibuja el panel entero plano. Por eso van los `nan*`."""
    scene = _scene_para_puntajes()
    angulos = np.linspace(0.16, 0.45, 64).reshape(8, 8)
    angulos[0, 0] = np.nan

    ax_mapa, _ax_hist = plot_score_map(angulos, scene)

    vmin, vmax = ax_mapa.images[0].get_clim()
    assert np.isfinite(vmin) and np.isfinite(vmax)
    assert vmin < vmax


def test_la_escala_de_color_se_recorta_por_percentiles_y_no_al_rango_cero_pi():
    """Los angulos reales ocupan una franja estrecha de [0, pi]: estirando el
    color sobre el rango completo el mapa sale de un solo tono."""
    scene = _scene_para_puntajes()
    angulos = np.linspace(0.16, 0.45, 64).reshape(8, 8)

    ax_mapa, _ax_hist = plot_score_map(angulos, scene)

    vmin, vmax = ax_mapa.images[0].get_clim()
    assert vmin > 0.16
    assert vmax < 0.45


def test_el_histograma_cuenta_solo_los_pixeles_validos():
    """Los NaN del enmascarado no son un angulo de cero: contarlos correria la
    distribucion hacia el extremo de "muy parecido"."""
    scene = _scene_para_puntajes()
    angulos = np.linspace(0.16, 0.45, 64).reshape(8, 8)
    angulos[:2] = np.nan  # 16 de 64 pixeles invalidos

    _ax_mapa, ax_hist = plot_score_map(angulos, scene)

    total = sum(parche.get_height() for parche in ax_hist.patches)
    assert total == 48


def test_un_mapa_de_forma_distinta_a_la_del_scene_es_un_error():
    """Los ejes saldrian con las coordenadas de otra ventana del tile."""
    scene = _scene_para_puntajes(alto=8, ancho=8)

    with pytest.raises(ValueError, match=r"\(4, 4\).*\(8, 8\)"):
        plot_score_map(np.zeros((4, 4)), scene)
