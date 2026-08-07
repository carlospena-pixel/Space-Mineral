"""Pruebas del constructor de Scene sobre la escena Sentinel-2 real.

Son los unicos tests del proyecto que necesitan el producto .SAFE descargado;
en una copia limpia del repo se omiten en vez de fallar.
"""

import glob

import numpy as np
import pytest
from rasterio.windows import Window

from mineralmap.config import BAND_ORDER, SAM_BANDS
from mineralmap.io.raster_io import find_band_file, find_safe_dir
from mineralmap.preprocessing.masking import apply_mask
from mineralmap.preprocessing.scene_builder import build_scene_from_safe
from mineralmap.spectral.endmembers import get_reference_spectrum

pytestmark = pytest.mark.skipif(
    not glob.glob("data/raw/**/*.SAFE", recursive=True),
    reason="requiere la escena Sentinel-2 en data/raw/",
)

# Ventana chica: alcanza para validar el contrato sin leer 40x40 km.
VENTANA_PRUEBA = Window(col_off=1000, row_off=1000, width=64, height=64)


@pytest.fixture(scope="module")
def scene():
    """Scene de 12 bandas sobre una ventana de 64x64 px."""
    return build_scene_from_safe(aoi=VENTANA_PRUEBA, verbose=False)


def test_find_band_file_resuelve_la_resolucion_nativa_de_cada_banda():
    """B8 solo existe a 10 m y B9 solo a 60 m; el resto es nativo a 20 m."""
    safe_dir = find_safe_dir("data/raw/")

    assert find_band_file(safe_dir, "B8")[1] == 10
    assert find_band_file(safe_dir, "B9")[1] == 60
    for banda in ("B2", "B11", "B12", "SCL"):
        assert find_band_file(safe_dir, banda)[1] == 20


def test_scene_cumple_el_contrato_de_bandas_y_georreferenciacion(scene):
    """Cubo (12, 64, 64) float32, bandas en el orden del contrato, UTM 19S."""
    assert scene.cube.shape == (12, 64, 64)
    assert scene.cube.dtype == np.float32
    assert scene.band_names == BAND_ORDER
    assert scene.crs.to_epsg() == 32719

    assert scene.mask.shape == (64, 64)
    assert scene.mask.dtype == np.bool_

    assert scene.meta["tile_id"] == "T19KDT"
    assert scene.meta["processing_baseline"]
    assert scene.meta["aoi_window"] == [1000, 1000, 64, 64]
    assert scene.meta["bands_source"]["B8"] == 10
    assert scene.meta["bands_source"]["B9"] == 60


def test_todas_las_bandas_traen_senal_en_rango(scene):
    """Reflectancia en [0,1] o NaN, y ninguna banda constante cero.

    Una banda entera en cero es la firma de una lectura fallida silenciosa
    (ventana fuera del raster, resolucion equivocada), no de un dato real.
    """
    for indice, banda in enumerate(scene.band_names):
        capa = scene.cube[indice]
        finitos = capa[~np.isnan(capa)]

        assert finitos.size > 0, f"{banda} quedo enteramente NaN"
        assert finitos.min() >= 0.0, f"{banda} tiene reflectancia negativa"
        assert finitos.max() <= 1.0, f"{banda} tiene reflectancia > 1"
        assert np.any(finitos > 0.0), f"{banda} es constante cero"


def test_la_firma_de_referencia_calza_con_el_cubo_real(scene):
    """El cubo y la firma tienen que traer el mismo numero de bandas.

    Es la frontera entre `preprocessing` y `spectral`, y es la que el SAM
    asume sin poder comprobarla: `np.einsum("bhw,b->hw", cube, reference)`
    exige que los dos ejes `b` sean el mismo. Si no lo fueran, numpy si
    fallaria, pero recien al calcular; lo que este test protege es que el
    contrato se compruebe aqui, sobre el producto real y no sobre BAND_ORDER
    escrito a mano.
    """
    firma = get_reference_spectrum("kaolinite", band_order=scene.band_names)

    assert scene.band_names == BAND_ORDER
    assert firma.shape == (scene.cube.shape[0],)
    assert np.all(np.isfinite(firma))


def test_apply_mask_sobre_el_cubo_real_no_borra_el_aoi_ni_lo_muta(scene):
    """Enmascarar no puede dejar el AOI entero en NaN, y no toca el original.

    Los dos modos de fallar son opuestos y ninguno lanza excepcion. Una
    mascara invertida (la convencion es True = valido, no True = nube) dejaria
    el AOI completo en NaN sobre este desierto despejado. Y si `apply_mask`
    trabajara in place, el `Scene` perderia el cubo crudo para siempre: un
    pixel que paso a NaN no se recupera sin releer el producto.
    """
    nan_originales = int(np.isnan(scene.cube).sum())

    enmascarado = apply_mask(scene.cube, scene.mask)

    assert enmascarado is not scene.cube
    assert int(np.isnan(scene.cube).sum()) == nan_originales

    validos = np.isfinite(enmascarado).all(axis=0)
    assert validos.any(), "apply_mask dejo el AOI entero en NaN"
    # Este AOI es desierto despejado: la mascara no deberia quitar casi nada.
    assert validos.sum() == int(scene.mask.sum())


def test_el_subconjunto_sam_bands_del_cubo_sigue_alineado_con_su_firma(scene):
    """Subconjuntar el cubo por indice y pedir la firma por nombre coinciden.

    Es el paso que va a dar el detector cuando pase a consumir SAM_BANDS: el
    cubo se recorta por indices posicionales y la firma se pide por nombres.
    Son dos caminos distintos hacia la misma banda, y nada los obliga a
    coincidir. Si divergieran, el SAM compararia la reflectancia de B11 contra
    el valor de referencia de B12 y devolveria un mapa perfectamente calculado
    y sin sentido.
    """
    indices = [scene.band_names.index(banda) for banda in SAM_BANDS]
    cubo_sam = scene.cube[indices]
    firma_sam = get_reference_spectrum("kaolinite", band_order=SAM_BANDS)
    firma_completa = get_reference_spectrum("kaolinite", band_order=scene.band_names)

    assert cubo_sam.shape == (len(SAM_BANDS),) + scene.cube.shape[1:]
    assert firma_sam.shape == (len(SAM_BANDS),)

    for posicion, banda in enumerate(SAM_BANDS):
        indice_original = scene.band_names.index(banda)
        # La capa del subconjunto es exactamente la del cubo completo...
        np.testing.assert_array_equal(
            cubo_sam[posicion], scene.cube[indice_original], err_msg=banda
        )
        # ...y el valor de la firma en esa misma posicion, tambien.
        assert firma_sam[posicion] == firma_completa[indice_original], banda
