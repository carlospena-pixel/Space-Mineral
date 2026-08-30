"""Orquestador: encadena los pasos (preprocessing -> spectral -> algorithms ->
validation -> visualization) segun lo definido en un Config.

Es el unico lugar donde se ve el flujo completo.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
from rasterio.windows import Window

from mineralmap.algorithms.base import Detector
from mineralmap.algorithms.sam import SAM
from mineralmap.config import Config
from mineralmap.io.raster_io import Scene, load_scene, save_scene, write_geotiff
from mineralmap.preprocessing.masking import apply_mask
from mineralmap.preprocessing.scene_builder import (
    DEFAULT_AOI_WINDOW,
    build_scene_from_safe,
)
from mineralmap.spectral.endmembers import get_reference_spectrum
from mineralmap.visualization.maps import plot_score_map

# Registro de detectores: `algorithm.name` del YAML -> clase que implementa
# `Detector`. Es el mecanismo de escalabilidad del proyecto (decisiones
# tecnicas 1.2): pasar a Random Forest tiene que ser agregar una clase y una
# entrada aca, no reescribir el flujo.
#
# Para que eso sea cierto, el encadenado le pregunta al detector todo lo que
# antes daba por sentado de SAM: que bandas consume (`detector.bands`) y en que
# direccion apunta su puntaje (`detector.detects`). Este modulo no importa
# SAM_BANDS ni `threshold`, y esa ausencia es la prueba de que el acoplamiento
# se fue. Lo que quedaba antes no fallaba ruidosamente: un detector que
# devolviera evidencia maxima en todo el AOI se reportaba como cero
# detecciones, porque el `<=` de SAM se aplicaba a cualquier puntaje.
DETECTORS: dict[str, type[Detector]] = {"sam": SAM}

# Umbrales del barrido que acompana al resumen. No son candidatos a
# configuracion: son la evidencia de que el umbral del config es uno de muchos
# y de cuantos pixeles caeria bajo cada uno. Sin este barrido, un resultado de
# cero detecciones no se distingue de un error de calculo.
#
# Siguen expresados en radianes, o sea que son especificos del angulo espectral
# igual que la clave `angle_threshold_rad` del config. Generalizarlos antes de
# saber que unidades trae el segundo detector seria especular; lo que importa
# es que ninguno de los dos produce un resultado equivocado en silencio, porque
# la comparacion la hace `detector.detects`. Ver decisiones tecnicas seccion 8.
THRESHOLD_SWEEP: tuple[float, ...] = (0.05, 0.08, 0.10, 0.15, 0.20)

# Cache del Scene. Es el mismo archivo que escribe scripts/construir_scene.py:
# el Scene de un AOI dado es siempre el mismo, y releer el .SAFE completo son
# minutos frente a segundos de .npz.
DEFAULT_SCENE_CACHE = "data/interim/scene.npz"

# Nombres de salida cuando el config no los declara. El experimento concreto
# los sobreescribe (ver configs/cerro_colorado_kaolinite.yaml); estos existen para
# que un config minimo produzca archivos con un nombre honesto en vez de
# fallar por una clave ausente.
DEFAULT_MAPS_DIR = "outputs/maps/"
DEFAULT_FIGURES_DIR = "outputs/figures/"
DEFAULT_ANGLE_MAP_NAME = "score_map.tif"
DEFAULT_HEATMAP_NAME = "score_map.png"


def _normalizar_root_escena(path: str | os.PathLike[str]) -> str:
    """Devuelve el directorio raiz donde `find_safe_dir` debe buscar el .SAFE.

    Los configs del proyecto apuntan `scene.path` a la carpeta `.SAFE` misma,
    que es lo que un humano escribe cuando quiere nombrar una escena concreta.
    `find_safe_dir(root)` en cambio busca carpetas `.SAFE` **bajo** `root`, asi
    que pasarle la ruta del producto no encuentra nada y aborta con un
    FileNotFoundError que culpa a la escena de estar ausente cuando esta ahi.
    La normalizacion vive aca y no en `find_safe_dir` para no cambiarle el
    contrato a una funcion que ya tiene tests y otros consumidores.

    Parameters
    ----------
    path:
        Ruta declarada en `scene.path`: un directorio raiz (`data/raw/`) o la
        carpeta `.SAFE` del producto.

    Returns
    -------
    str
        El directorio donde buscar. Si `path` termina en `.SAFE`, su padre.
    """
    ruta = Path(str(path))
    if ruta.suffix.upper() == ".SAFE":
        return str(ruta.parent)
    return str(ruta)


def _resolver_aoi(
    aoi: dict[str, Any],
) -> Window | tuple[float, float, float, float] | None:
    """Traduce la seccion `aoi` del config a lo que espera el constructor.

    `window_px` es autoritativo y `bbox` es informativo: la ventana esta
    expresada en la grilla de 20 m del tile, que es la definicion exacta del
    AOI, mientras que el bbox en WGS84 es su equivalente redondeado. Cuando
    estan los dos y difieren, ganar el bbox correria el recorte unos pixeles
    sin que nada lo denuncie.

    Parameters
    ----------
    aoi:
        Seccion `aoi` del Config. Puede traer `window_px` (dict con `col_off`,
        `row_off`, `width` y `height`), `bbox` (lista de 4 numeros en WGS84),
        ambos o ninguno.

    Returns
    -------
    Window | tuple | None
        La ventana si hay `window_px`; el bbox como tupla si solo hay `bbox`;
        None si no hay ninguno (el constructor usa entonces su ventana por
        defecto).

    Raises
    ------
    ValueError
        Si `window_px` no trae las cuatro claves, o si `bbox` no trae cuatro
        valores.
    """
    window_px = aoi.get("window_px")
    if window_px:
        claves = ("col_off", "row_off", "width", "height")
        faltantes = [clave for clave in claves if clave not in window_px]
        if faltantes:
            raise ValueError(
                f"aoi.window_px necesita {list(claves)}; faltan {faltantes} "
                f"(recibi {window_px})."
            )
        return Window(**{clave: int(window_px[clave]) for clave in claves})

    bbox = aoi.get("bbox")
    if bbox:
        if len(bbox) != 4:
            raise ValueError(
                f"aoi.bbox debe tener 4 valores "
                f"(min_lon, min_lat, max_lon, max_lat); recibi {bbox!r}."
            )
        return tuple(float(valor) for valor in bbox)

    return None


def _crear_detector(name: str) -> Detector:
    """Instancia el detector registrado bajo `name`.

    Parameters
    ----------
    name:
        Valor de `algorithm.name` en el YAML del experimento.

    Returns
    -------
    Detector
        Instancia nueva de la clase registrada.

    Raises
    ------
    KeyError
        Si el nombre no esta en DETECTORS. El mensaje lista los disponibles:
        un typo en el YAML tiene que nombrarse a si mismo, no salir como un
        KeyError pelado en medio de una corrida de varios minutos.
    """
    if name not in DETECTORS:
        raise KeyError(
            f"El algoritmo '{name}' no esta registrado; los disponibles son "
            f"{sorted(DETECTORS)}. Para agregar uno: una clase en "
            f"mineralmap/algorithms/ y una entrada en DETECTORS."
        )
    return DETECTORS[name]()


def _cache_coincide(
    scene: Scene,
    aoi: Window | tuple[float, float, float, float] | None,
    band_names: list[str],
) -> tuple[bool, str]:
    """Dice si el Scene cacheado es el que pide el config, y por que no.

    Un cache que se usa sin comprobar la ventana es el peor modo de fallo del
    pipeline: corre entero, escribe un GeoTIFF valido y el mapa es de otro
    AOI. Preferimos releer el producto a arriesgar eso, asi que todo lo que no
    se pueda verificar se trata como no coincidente.

    La ventana se compara contra `meta["aoi_window"]`. `meta` sigue siendo
    documentacion y no configuracion (decisiones tecnicas 1.1): el AOI viene
    del config en todos los caminos, y lo unico que `meta` puede hacer aca es
    **vetar** el cache. Si falta o no calza, se reconstruye.

    Parameters
    ----------
    scene:
        Scene cargado desde el cache.
    aoi:
        AOI pedido por el config, ya resuelto por `_resolver_aoi`.
    band_names:
        Bandas pedidas por el config, en orden.

    Returns
    -------
    tuple[bool, str]
        (sirve, motivo). `motivo` es la cadena que se imprime cuando no sirve.
    """
    if list(scene.band_names) != list(band_names):
        return False, (
            f"las bandas del cache {scene.band_names} no son las del config "
            f"{band_names}"
        )

    if aoi is None:
        ventana = DEFAULT_AOI_WINDOW
    elif isinstance(aoi, Window):
        ventana = aoi
    else:
        # Con un bbox, la ventana efectiva la resuelve `_resolver_ventana`
        # dentro del constructor reproyectando y redondeando a pixeles: aca no
        # se puede predecir sin abrir el producto, asi que no se cachea.
        return False, "el AOI viene como bbox y la ventana efectiva no es verificable"

    esperada = [
        int(ventana.col_off),
        int(ventana.row_off),
        int(ventana.width),
        int(ventana.height),
    ]
    guardada = scene.meta.get("aoi_window")
    if guardada is None:
        return False, "el cache no registra su ventana (meta['aoi_window'] ausente)"
    if list(guardada) != esperada:
        return (
            False,
            f"la ventana del cache {list(guardada)} no es la del config {esperada}",
        )

    return True, ""


def _resolver_scene(
    config: Config, use_cache: bool | None = None
) -> tuple[Scene, str | None]:
    """Carga el Scene del cache si sirve, y si no lo construye desde el .SAFE.

    Parameters
    ----------
    config:
        Config del experimento.
    use_cache:
        None deja decidir a `preprocessing.cache_scene` (default True); True o
        False lo fuerzan (es lo que hace `--no-cache` en la CLI).

    Returns
    -------
    tuple[Scene, str | None]
        El Scene y la ruta del .npz si se escribio o se leyo, None si no se
        uso cache.
    """
    aoi = _resolver_aoi(config.aoi)
    band_names = list(config.scene.get("bands") or [])
    root = _normalizar_root_escena(config.scene.get("path", "data/raw/"))

    cachear = config.preprocessing.get("cache_scene", True)
    if use_cache is not None:
        cachear = use_cache
    ruta_cache = str(config.preprocessing.get("scene_cache", DEFAULT_SCENE_CACHE))

    if cachear and os.path.exists(ruta_cache):
        scene = load_scene(ruta_cache)
        sirve, motivo = _cache_coincide(scene, aoi, band_names)
        if sirve:
            print(f"Scene desde el cache {ruta_cache}")
            return scene, ruta_cache
        print(f"Ignoro el cache {ruta_cache}: {motivo}. Reconstruyo desde {root}.")

    scene = build_scene_from_safe(root=root, band_names=band_names, aoi=aoi)

    if cachear:
        Path(ruta_cache).parent.mkdir(parents=True, exist_ok=True)
        save_scene(scene, ruta_cache)
        print(f"Scene cacheado en {ruta_cache}")
        return scene, ruta_cache

    return scene, None


def _estadisticas_del_mapa(score_map: np.ndarray) -> dict[str, float]:
    """Minimo, percentil 1, mediana y maximo de los puntajes validos.

    Todo con la variante `nan*`: el mapa llega con NaN en lo enmascarado, y
    `np.min` sobre el devolveria NaN para las cuatro cifras sin avisar.
    """
    return {
        "min": float(np.nanmin(score_map)),
        "p1": float(np.nanpercentile(score_map, 1)),
        "median": float(np.nanmedian(score_map)),
        "max": float(np.nanmax(score_map)),
    }


def _barrido_de_umbrales(
    score_map: np.ndarray, mask: np.ndarray, detector: Detector
) -> dict[float, dict[str, float]]:
    """Pixeles y porcentaje del AOI valido bajo cada umbral del barrido.

    La comparacion la hace `detector.detects` y no un `<=` escrito aca: el
    sentido del umbral depende de la direccion que declare el detector, y
    fijarlo en el pipeline reportaba cero detecciones para cualquier detector
    donde mayor es mejor, sin lanzar nada.

    El `& mask` no es redundante con los NaN: toda comparacion contra NaN es
    falsa, pero dejarlo explicito hace que el porcentaje se lea siempre contra
    el mismo denominador (los validos) y no contra el AOI entero.
    """
    validos = int(mask.sum())
    barrido: dict[float, dict[str, float]] = {}

    for umbral in THRESHOLD_SWEEP:
        detectados = int((detector.detects(score_map, umbral) & mask).sum())
        barrido[umbral] = {
            "pixels": detectados,
            "pct": 100.0 * detectados / validos if validos else 0.0,
        }

    return barrido


def _imprimir_resumen(resultado: dict[str, Any]) -> None:
    """Imprime el resumen del experimento: forma, bandas, angulos y umbrales."""
    angulo = resultado["angle"]
    print("=" * 68)
    print(f"Mineral objetivo : {resultado['mineral']}")
    print(f"Algoritmo        : {resultado['algorithm']}")
    print(f"Forma del mapa   : {resultado['shape']}")
    print(f"Bandas usadas    : {resultado['bands']}")
    print(f"Pixeles validos  : {resultado['valid_px']:,}")
    print(
        f"Angulo (rad)     : min {angulo['min']:.4f} | p1 {angulo['p1']:.4f} | "
        f"mediana {angulo['median']:.4f} | max {angulo['max']:.4f}"
    )
    print("Barrido de umbrales:")
    for umbral, cuenta in resultado["threshold_sweep"].items():
        print(
            f"  umbral {umbral:.2f} rad -> {cuenta['pixels']:>9,} px  "
            f"({cuenta['pct']:.3f} % del AOI valido)"
        )

    umbral_config = resultado["threshold_rad"]
    detectados = resultado["detected_px"]
    if detectados == 0:
        # Cero detecciones es un resultado medido, no una falla del codigo: el
        # entregable de esta etapa es el mapa de angulos, y el mapa se escribe
        # igual. Tratarlo como error escondería justamente lo que hay que ver.
        print(
            f"Resultado        : 0 pixeles bajo el umbral {umbral_config} rad "
            f"del config. El mapa de angulos se escribe igual: es el "
            f"entregable, y el umbral espera un criterio de calibracion."
        )
    else:
        pct = 100.0 * detectados / resultado["valid_px"]
        print(
            f"Resultado        : {detectados:,} px bajo el umbral "
            f"{umbral_config} rad ({pct:.3f} % del AOI valido)"
        )
    print("=" * 68)


def _guardar_heatmap(
    score_map: np.ndarray, scene: Scene, path: str, mineral: str | None
) -> None:
    """Dibuja el mapa de puntaje con `plot_score_map` y lo guarda como PNG."""
    import matplotlib.pyplot as plt

    tile = scene.meta.get("tile_id", "")
    fecha = str(scene.meta.get("sensing_date", ""))[:10]
    ejes = plot_score_map(
        score_map, scene, title=f"{mineral} - AOI {tile} {fecha}".strip()
    )

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    figura = ejes[0].figure
    figura.savefig(path, dpi=150, bbox_inches="tight")
    # Cerrar la figura y no dejarla al recolector: `run_pipeline` es una
    # funcion de libreria y un notebook que la llame varias veces acumularia
    # figuras abiertas hasta el aviso de matplotlib.
    plt.close(figura)


def run_pipeline(config: Config, use_cache: bool | None = None) -> dict[str, Any]:
    """Corre el experimento completo descrito por `config` y escribe sus salidas.

    Encadena: resolver el Scene (cache o `.SAFE`) -> enmascarar -> subconjuntar
    a las bandas que declara el detector -> firma de referencia en ese mismo
    orden -> detector -> GeoTIFF + heatmap.

    El flujo no sabe que algoritmo esta corriendo: lo instancia desde
    `algorithm.name` a traves de DETECTORS y despues le pregunta lo que
    necesita saber. `detector.bands` fija el subconjunto del cubo y el orden de
    la firma; `detector.detects` decide de que lado del umbral cae una
    deteccion. Las dos cosas estaban fijadas a SAM, y la segunda fallaba en
    silencio: un detector donde mayor es mejor se reportaba con cero
    detecciones bajo todos los umbrales.

    Parameters
    ----------
    config:
        Config cargado con `load_config`.
    use_cache:
        None respeta `preprocessing.cache_scene`; True o False lo fuerzan.

    Returns
    -------
    dict
        Rutas escritas (`angle_map_path`, `heatmap_path`, `scene_cache_path`)
        y las estadisticas del mapa (`shape`, `bands`, `valid_px`, `angle`,
        `threshold_sweep`, `threshold_rad`, `detected_px`). La funcion
        devuelve datos y el script de CLI es el que imprime.

    Raises
    ------
    KeyError
        Si `algorithm.name` no esta registrado, o si el mineral no tiene firma.
    ValueError
        Si el detector declara en `bands` alguna banda que el Scene no trae.
    FileNotFoundError
        Si no hay producto `.SAFE` bajo `scene.path` y el cache no sirve.
    """
    scene, ruta_cache = _resolver_scene(config, use_cache=use_cache)

    # El cubo se enmascara aqui y no en el constructor: `Scene` guarda el cubo
    # crudo y la validez aparte, y aplicarla es decision del consumidor.
    cubo = apply_mask(scene.cube, scene.mask)

    # El detector se instancia ANTES de subconjuntar porque es el que dice que
    # bandas quiere. Antes el pipeline recortaba a SAM_BANDS incondicionalmente
    # y un detector con otras necesidades espectrales recibia igual esas nueve.
    detector = _crear_detector(config.algorithm.get("name", ""))
    bandas = list(detector.bands) if detector.bands else list(scene.band_names)

    # `list.index` lanza "'B99' is not in list", que es ruidoso pero anonimo:
    # no dice quien pidio esa banda ni contra que Scene. Es la superficie que
    # estrena `detector.bands`, y el repositorio ya se exige nombrar el origen
    # en `_crear_detector` y en `find_band_file`.
    faltantes = [banda for banda in bandas if banda not in scene.band_names]
    if faltantes:
        raise ValueError(
            f"El detector {type(detector).__name__} declara en `bands` las "
            f"bandas {faltantes}, que no estan en el Scene "
            f"({scene.band_names}). Revisa el atributo `bands` del detector o "
            f"las bandas que pide el config en `scene.bands`."
        )

    # El subconjunto va por indice y la firma por nombre, con la misma lista:
    # el contrato del cubo es posicional (decisiones tecnicas 1.1) y son dos
    # caminos distintos hacia la misma banda. Si divergieran, el detector
    # compararia la reflectancia de una banda contra la referencia de otra y
    # devolveria un mapa perfectamente calculado y sin sentido.
    indices = [scene.band_names.index(banda) for banda in bandas]
    cubo = cubo[indices].astype(np.float64)

    mineral = config.mineral.get("target")
    referencia = get_reference_spectrum(mineral, band_order=bandas)

    puntajes = detector.predict(cubo, referencia)

    # NaN donde el pixel es invalido. El detector ya propaga los NaN del cubo,
    # pero un detector futuro podria no hacerlo (un Random Forest imputa), y
    # entonces el mapa traeria un puntaje inventado sobre nubes y agua.
    puntajes = np.where(scene.mask, puntajes, np.nan)

    salida = config.output
    ruta_mapa = os.path.join(
        salida.get("maps_dir", DEFAULT_MAPS_DIR),
        salida.get("angle_map", DEFAULT_ANGLE_MAP_NAME),
    )
    ruta_heatmap = os.path.join(
        salida.get("figures_dir", DEFAULT_FIGURES_DIR),
        salida.get("heatmap", DEFAULT_HEATMAP_NAME),
    )

    write_geotiff(
        ruta_mapa,
        puntajes,
        scene,
        band_descriptions=[f"{config.algorithm.get('name')}_angle_rad_{mineral}"],
    )

    _guardar_heatmap(puntajes, scene, ruta_heatmap, mineral)

    umbral_config = float(
        config.algorithm.get("params", {}).get("angle_threshold_rad", float("nan"))
    )

    resultado: dict[str, Any] = {
        "angle_map_path": ruta_mapa,
        "heatmap_path": ruta_heatmap,
        "scene_cache_path": ruta_cache,
        "mineral": mineral,
        "algorithm": config.algorithm.get("name"),
        "shape": tuple(int(v) for v in puntajes.shape),
        "bands": bandas,
        "valid_px": int(scene.mask.sum()),
        "angle": _estadisticas_del_mapa(puntajes),
        "threshold_sweep": _barrido_de_umbrales(puntajes, scene.mask, detector),
        "threshold_rad": umbral_config,
        "detected_px": int(
            (detector.detects(puntajes, umbral_config) & scene.mask).sum()
        ),
    }

    _imprimir_resumen(resultado)
    return resultado
