"""Pruebas del orquestador que corren sin el producto .SAFE.

`run_pipeline` sobre la escena real necesita el .SAFE y varios minutos. Lo que
se cubre aca es todo lo que decide antes o alrededor de leer el cubo --resolver
el AOI, normalizar la ruta de la escena, instanciar el detector, aceptar o
vetar el cache-- y la agnosticidad del flujo respecto del detector, que se
prueba con un Scene sintetico y un detector ficticio.

El backend "Agg" se fija antes de importar pyplot para que el guardado del
heatmap corra sin display (CI incluido).
"""

from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

from affine import Affine  # noqa: E402
from rasterio.crs import CRS  # noqa: E402
from rasterio.windows import Window  # noqa: E402

from mineralmap.algorithms.base import Detector  # noqa: E402
from mineralmap.algorithms.sam import SAM  # noqa: E402
from mineralmap.config import Config  # noqa: E402
from mineralmap.io.raster_io import Scene  # noqa: E402
from mineralmap.pipeline import (  # noqa: E402
    DETECTORS,
    _barrido_de_umbrales,
    _cache_coincide,
    _crear_detector,
    _normalizar_root_escena,
    _resolver_aoi,
    run_pipeline,
)
from mineralmap.spectral.endmembers import get_reference_spectrum  # noqa: E402

# La ventana del AOI del proyecto, tal como la declara
# configs/tamarugal_kaolinite.yaml.
WINDOW_PX = {"col_off": 1000, "row_off": 1000, "width": 2000, "height": 2000}
BBOX_TAMARUGAL = [-69.7673, -20.4377, -69.383, -20.075]

# Ventana por defecto de `build_scene_from_safe`, que es contra la que se
# compara el cache cuando el config no declara AOI.
VENTANA_DEFAULT = [1000, 1000, 2000, 2000]


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


# --- Agnosticidad del flujo respecto del detector -------------------------


class DetectorFicticio(Detector):
    """Detector de prueba: devuelve una constante y registra lo que recibio.

    Existe para representar al segundo detector del proyecto (Random Forest,
    Nivel 2) antes de que exista: uno que respeta el contrato --mayor valor,
    mayor evidencia-- y que no consume las bandas de SAM.
    """

    higher_is_better = True
    bands = None

    def __init__(self, valor: float = 0.9, bands=None):
        self.valor = valor
        self.bands = bands
        self.recibido: dict = {}

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        self.recibido = {"cube": np.asarray(cube), "reference": np.asarray(reference)}
        return np.full(cube.shape[1:], self.valor)


def _scene_sintetico(band_names, alto=8, ancho=8, aoi_window=None):
    """Scene minimo con una banda constante por posicion, para trazar el orden."""
    cube = np.stack(
        [np.full((alto, ancho), 0.1 * (i + 1)) for i in range(len(band_names))]
    ).astype(np.float32)
    meta = {} if aoi_window is None else {"aoi_window": list(aoi_window)}
    return Scene(
        cube=cube,
        band_names=list(band_names),
        transform=Affine(20.0, 0.0, 420000.0, 0.0, -20.0, 7780000.0),
        crs=CRS.from_epsg(32719),
        mask=np.ones((alto, ancho), dtype=bool),
        meta=meta,
    )


def test_el_pipeline_respeta_la_direccion_declarada_por_el_detector():
    """Un puntaje donde mayor es mejor no puede reportarse con el `<=` de SAM.

    Es el modo de falla que motivo `Detector.detects`. El pipeline aplicaba el
    umbral con el sentido del angulo espectral a la salida de cualquier
    detector: uno que devolviera evidencia maxima en todo el AOI se reportaba
    como cero detecciones bajo los cinco umbrales del barrido, sin lanzar nada.
    Se habria descubierto el dia del primer commit del segundo detector, con el
    pipeline entero corriendo y reportando cero.
    """
    detector = DetectorFicticio(valor=0.9)
    puntajes = np.full((4, 4), 0.9)
    mascara = np.ones((4, 4), dtype=bool)

    barrido = _barrido_de_umbrales(puntajes, mascara, detector)

    # 0,9 supera los cinco umbrales, asi que los 16 pixeles son deteccion.
    assert all(cuenta["pixels"] == 16 for cuenta in barrido.values())

    # Y el mismo mapa con la direccion de SAM da lo contrario, que es lo que
    # el pipeline reportaba antes para cualquier detector.
    assert all(
        cuenta["pixels"] == 0
        for cuenta in _barrido_de_umbrales(puntajes, mascara, SAM()).values()
    )


def test_el_pipeline_subconjunta_con_las_bandas_que_declara_el_detector(
    tmp_path, monkeypatch
):
    """El cubo y la firma se arman con `detector.bands`, no con SAM_BANDS.

    Antes el pipeline recortaba a las nueve bandas de SAM incondicionalmente:
    un detector con otras necesidades espectrales recibia igual esas nueve y
    calculaba sobre bandas que no habia pedido, sin ningun error. El orden
    tambien importa y por eso el detector de prueba pide sus bandas al reves
    del orden del Scene: el cubo se subconjunta por indice y la firma se pide
    por nombre, y si divergieran el detector compararia la reflectancia de una
    banda contra la referencia de otra.
    """
    band_names = ["B2", "B3", "B4", "B11", "B12"]
    scene = _scene_sintetico(band_names)
    detector = DetectorFicticio(bands=("B12", "B4"))

    monkeypatch.setitem(DETECTORS, "ficticio", lambda: detector)
    monkeypatch.setattr(
        "mineralmap.pipeline._resolver_scene",
        lambda config, use_cache=None: (scene, None),
    )

    config = Config(
        scene={"bands": band_names},
        mineral={"target": "kaolinite"},
        algorithm={"name": "ficticio", "params": {"angle_threshold_rad": 0.1}},
        output={
            "maps_dir": str(tmp_path),
            "figures_dir": str(tmp_path),
            "angle_map": "mapa.tif",
            "heatmap": "mapa.png",
        },
    )

    resultado = run_pipeline(config)

    assert resultado["bands"] == ["B12", "B4"]
    assert detector.recibido["cube"].shape[0] == 2

    # La capa 0 del cubo que recibio es la banda B12 del Scene, no la primera.
    np.testing.assert_allclose(
        detector.recibido["cube"][0], scene.cube[band_names.index("B12")]
    )
    np.testing.assert_allclose(
        detector.recibido["reference"],
        get_reference_spectrum("kaolinite", band_order=["B12", "B4"]),
    )


def test_pedir_una_banda_que_el_scene_no_trae_nombra_al_detector(tmp_path, monkeypatch):
    """El error tiene que decir quien pidio la banda, no solo que falta.

    `scene.band_names.index(banda)` lanza "'B99' is not in list": es ruidoso,
    asi que no es un fallo silencioso, pero es anonimo. No dice que la pidio el
    detector via `bands`, ni cuales trae el Scene, asi que hay que abrir el
    codigo para saber donde esta el problema. Sin este test nada obliga a que
    el mensaje siga nombrando al detector y a la banda: basta con que alguien
    simplifique el chequeo a un `assert` para volver al mensaje de numpy, y el
    test seguiria pasando si solo comprobara que lanza ValueError.
    """
    band_names = ["B2", "B3", "B4"]
    scene = _scene_sintetico(band_names)
    detector = DetectorFicticio(bands=("B2", "B99"))

    monkeypatch.setitem(DETECTORS, "ficticio", lambda: detector)
    monkeypatch.setattr(
        "mineralmap.pipeline._resolver_scene",
        lambda config, use_cache=None: (scene, None),
    )

    config = Config(
        scene={"bands": band_names},
        mineral={"target": "kaolinite"},
        algorithm={"name": "ficticio", "params": {"angle_threshold_rad": 0.1}},
        output={"maps_dir": str(tmp_path), "figures_dir": str(tmp_path)},
    )

    with pytest.raises(ValueError) as excinfo:
        run_pipeline(config)

    mensaje = str(excinfo.value)
    assert "B99" in mensaje, "el mensaje no nombra la banda que falta"
    assert "DetectorFicticio" in mensaje, "el mensaje no nombra al detector"
    assert "bands" in mensaje, "el mensaje no dice de que atributo salio"
    # Y no nombra las que si estaban: el error es B99, no B2.
    assert "['B99']" in mensaje


def test_detects_por_defecto_sigue_el_sentido_del_contrato():
    """Un detector que no declara nada hereda "mayor es mejor"; SAM declara lo
    contrario porque su puntaje es el angulo.

    Sin el default, cada detector nuevo tendria que acordarse de declarar la
    direccion y olvidarlo daria cero detecciones en silencio. Con el default,
    olvidarlo deja el sentido que el contrato ya documenta.
    """
    assert Detector.higher_is_better is True
    assert Detector.bands is None
    assert SAM.higher_is_better is False
    assert tuple(SAM.bands) == ("B2", "B3", "B4", "B5", "B6", "B7", "B8A", "B11", "B12")

    puntajes = np.array([0.05, 0.5, 0.95])
    np.testing.assert_array_equal(
        DetectorFicticio().detects(puntajes, 0.5), [False, True, True]
    )
    np.testing.assert_array_equal(SAM().detects(puntajes, 0.5), [True, True, False])


def test_detects_no_cuenta_los_nan_como_deteccion():
    """Un pixel sin dato no es una deteccion, en ninguna de las dos
    direcciones. Sale gratis de IEEE-754 y por eso hay que fijarlo: una
    reimplementacion que "arreglara" los NaN antes de comparar los convertiria
    en detecciones con `higher_is_better = False`."""
    puntajes = np.array([np.nan, 0.5])

    assert not DetectorFicticio().detects(puntajes, 0.1)[0]
    assert not SAM().detects(puntajes, 0.9)[0]


# --- Verificacion del cache -----------------------------------------------


def test_el_cache_sirve_cuando_la_ventana_y_las_bandas_son_las_del_config():
    """El caso feliz: mismo AOI, mismas bandas, se reutiliza el .npz."""
    scene = _scene_sintetico(["B2", "B3"], aoi_window=WINDOW_PX.values())
    ventana = Window(**WINDOW_PX)

    sirve, motivo = _cache_coincide(scene, ventana, ["B2", "B3"])

    assert sirve
    assert motivo == ""


def test_un_cache_de_otra_ventana_se_rechaza():
    """Es el peor modo de fallo del proyecto: el pipeline corre entero, escribe
    un GeoTIFF valido y el mapa es de otro AOI. No lanza nada nunca."""
    scene = _scene_sintetico(["B2", "B3"], aoi_window=[0, 0, 2000, 2000])

    sirve, motivo = _cache_coincide(scene, Window(**WINDOW_PX), ["B2", "B3"])

    assert not sirve
    assert "ventana" in motivo


def test_un_cache_sin_ventana_registrada_se_rechaza():
    """Un .npz anterior a `meta["aoi_window"]` no se puede verificar, y lo que
    no se puede verificar se reconstruye: tres minutos de lectura son mas
    baratos que un mapa del AOI equivocado."""
    scene = _scene_sintetico(["B2", "B3"], aoi_window=None)

    sirve, motivo = _cache_coincide(scene, Window(**WINDOW_PX), ["B2", "B3"])

    assert not sirve
    assert "aoi_window" in motivo


def test_un_cache_con_otras_bandas_se_rechaza():
    """Mismo AOI pero otro cubo: el detector recibiria bandas que no pidio."""
    scene = _scene_sintetico(["B2", "B3"], aoi_window=WINDOW_PX.values())

    sirve, motivo = _cache_coincide(scene, Window(**WINDOW_PX), ["B2", "B3", "B4"])

    assert not sirve
    assert "bandas" in motivo


def test_con_el_aoi_dado_como_bbox_no_se_usa_el_cache():
    """La ventana efectiva de un bbox la resuelve el constructor reproyectando
    y redondeando a pixeles; aca no se puede predecir sin abrir el producto,
    asi que no se cachea en vez de adivinar."""
    scene = _scene_sintetico(["B2", "B3"], aoi_window=WINDOW_PX.values())

    sirve, motivo = _cache_coincide(scene, tuple(BBOX_TAMARUGAL), ["B2", "B3"])

    assert not sirve
    assert "bbox" in motivo


def test_sin_aoi_el_cache_se_compara_contra_la_ventana_por_defecto():
    """Cuando el config no declara AOI, `build_scene_from_safe` usa
    DEFAULT_AOI_WINDOW, asi que esa es la ventana que el cache tiene que traer
    para servir. Es predecible, y por eso si se cachea."""
    scene = _scene_sintetico(["B2", "B3"], aoi_window=VENTANA_DEFAULT)

    sirve, _motivo = _cache_coincide(scene, None, ["B2", "B3"])

    assert sirve
