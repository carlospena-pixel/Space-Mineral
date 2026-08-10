"""Pruebas de las piezas del orquestador que se pueden probar sin la escena.

`run_pipeline` completo necesita el producto .SAFE y varios minutos; lo que se
cubre aca son las tres decisiones que toma antes de tocar disco --resolver el
AOI, normalizar la ruta de la escena e instanciar el detector-- porque son las
que fallan en silencio o con un mensaje que no dice donde esta el problema.
"""

from pathlib import Path

import pytest
from rasterio.windows import Window

from mineralmap.algorithms.sam import SAM
from mineralmap.pipeline import (
    DETECTORS,
    _crear_detector,
    _normalizar_root_escena,
    _resolver_aoi,
)

# La ventana del AOI del proyecto, tal como la declara
# configs/tamarugal_kaolinite.yaml.
WINDOW_PX = {"col_off": 1000, "row_off": 1000, "width": 2000, "height": 2000}
BBOX_TAMARUGAL = [-69.7673, -20.4377, -69.383, -20.075]


def test_el_registro_resuelve_sam_desde_el_nombre_del_config():
    """El pipeline no conoce el algoritmo: lo instancia desde `algorithm.name`.

    Es el mecanismo de escalabilidad del proyecto (decisiones tecnicas 1.2):
    agregar Random Forest tiene que ser una clase mas y una entrada mas en
    DETECTORS, no un `if` en el flujo.
    """
    detector = _crear_detector("sam")

    assert isinstance(detector, SAM)
    assert "sam" in DETECTORS


def test_un_algoritmo_desconocido_es_un_keyerror_que_se_nombra():
    """Un typo en el YAML tiene que decir que nombre no existe y cuales si.

    Sin el mensaje, el error aparece como un KeyError pelado a los pocos
    segundos de una corrida que ya cargo la escena.
    """
    with pytest.raises(KeyError, match="random_forset"):
        _crear_detector("random_forset")


def test_window_px_se_convierte_en_una_window_de_rasterio():
    """Es el primer consumidor de `aoi.window_px`: hasta hoy nadie la leia."""
    ventana = _resolver_aoi({"window_px": WINDOW_PX})

    assert isinstance(ventana, Window)
    assert (ventana.col_off, ventana.row_off) == (1000, 1000)
    assert (ventana.width, ventana.height) == (2000, 2000)


def test_window_px_le_gana_al_bbox_cuando_estan_los_dos():
    """`window_px` es autoritativo y `bbox` es su equivalente informativo.

    El bbox esta redondeado a grados y el config declara los dos: si ganara el
    bbox, el recorte se correria unos pixeles respecto de la ventana que
    define el AOI, y nada lo denunciaria.
    """
    resuelto = _resolver_aoi({"window_px": WINDOW_PX, "bbox": BBOX_TAMARUGAL})

    assert isinstance(resuelto, Window)


def test_sin_window_px_se_usa_el_bbox():
    """Es el camino de configs/default.yaml, que no declara ventana."""
    resuelto = _resolver_aoi({"bbox": BBOX_TAMARUGAL})

    assert resuelto == tuple(BBOX_TAMARUGAL)


def test_sin_aoi_no_se_resuelve_nada_y_decide_el_constructor():
    """None es una respuesta valida: `build_scene_from_safe` cae entonces en
    DEFAULT_AOI_WINDOW, y duplicar ese default aca seria una segunda fuente de
    verdad que puede desincronizarse."""
    assert _resolver_aoi({}) is None
    assert _resolver_aoi({"bbox": None}) is None


def test_una_window_px_incompleta_es_un_error_que_nombra_lo_que_falta():
    """`Window(**dict)` sin `height` lanzaria un TypeError que habla de un
    argumento de rasterio, no del YAML que hay que arreglar."""
    with pytest.raises(ValueError, match="height"):
        _resolver_aoi({"window_px": {"col_off": 0, "row_off": 0, "width": 10}})


def test_la_ruta_de_un_safe_se_normaliza_a_su_directorio_padre():
    """Los configs apuntan `scene.path` a la carpeta .SAFE, pero
    `find_safe_dir(root)` busca carpetas .SAFE *bajo* `root`.

    Pasarle la ruta del producto no encuentra nada y aborta con un
    FileNotFoundError que culpa a la escena de no estar descargada cuando esta
    justo ahi. La normalizacion vive en el pipeline para no cambiarle el
    contrato a `find_safe_dir`, que ya tiene tests y otros consumidores.
    """
    safe = "data/raw/S2B_MSIL2A_20251231T144729_N0511_R139_T19KDT_20251231T200248.SAFE"

    assert Path(_normalizar_root_escena(safe)) == Path("data/raw")


def test_un_directorio_raiz_se_deja_como_esta():
    """El otro camino: `scene.path: data/raw/` de configs/default.yaml."""
    assert Path(_normalizar_root_escena("data/raw/")) == Path("data/raw")
