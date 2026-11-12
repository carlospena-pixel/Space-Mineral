"""Evaluacion de un mapa de puntaje: lectura, alineacion, metricas y reporte.

Es la capa que conecta las metricas puras (`metrics`, `capture`, `blocks`, que
solo ven arreglos de numpy) con los archivos del proyecto: GeoTIFF del mapa,
GeoTIFF de la verdad de terreno y archivos de puntos de porfidos. Aca vive todo
lo que necesita rasterio, rutas o el registro de detectores, para que
`scripts/evaluate.py` sea un parser de argumentos y nada mas.

Tres reglas que este modulo no negocia:

1. **Nunca reproyecta ni remuestrea en silencio.** Si el mapa y la verdad no
   comparten forma, CRS y transform, aborta diciendo que difiere. Alinear "por
   las dudas" produciria metricas impecables sobre pixeles que no se
   corresponden, que es el modo de falla que `io.raster_io.write_geotiff` ya
   evita del lado de la escritura.
2. **La direccion del puntaje no tiene default.** Se declara, o se deduce de un
   metadato que la declara (el config o la banda del GeoTIFF), o se aborta. Un
   AUC con la direccion invertida es ``1 - AUC``: un numero plausible y al reves.
3. **Los ambiguos (255) no se evaluan.** Ni como negativos ni como positivos.
   Ver `validation.geology`.
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import Affine

from mineralmap.spectral.indices import mask_by_positive_rate
from mineralmap.validation.blocks import block_metrics, summarize
from mineralmap.validation.capture import capture_rate
from mineralmap.validation.geology import CLASE_AMBIGUO, CLASE_NEGATIVO, CLASE_POSITIVO
from mineralmap.validation.metrics import (
    cohen_kappa,
    confusion_matrix,
    f1_score,
    iou_score,
    precision_recall,
    roc_auc,
    roc_curve,
    spatial_enrichment,
)

# Tolerancia para comparar transforms. Dos GeoTIFF escritos desde el mismo
# Scene traen el transform bit a bit igual; la tolerancia solo existe para que
# un redondeo de serializacion en el ultimo decimal no aborte una corrida
# legitima. 1e-9 de metro (o de grado) esta muy por debajo de cualquier
# desalineacion real, que se mide en fracciones de pixel de 20 m.
TOLERANCIA_TRANSFORM = 1e-9

# Nombres de columna aceptados en un CSV de puntos, en minusculas. Cubren las
# variantes en ingles y espanol que aparecen en las bases de depositos.
COLUMNAS_LAT = ("lat", "latitude", "latitud", "y")
COLUMNAS_LON = ("lon", "lng", "long", "longitude", "longitud", "x")


class AlignmentError(ValueError):
    """Los dos rasteres no estan en la misma grilla."""


class RasterBand(NamedTuple):
    """Una banda de un GeoTIFF con la georreferenciacion que la ubica."""

    data: np.ndarray  # float64, NaN donde el archivo declara nodata
    crs: CRS | None
    transform: Affine
    description: str | None  # descripcion de la banda, si el archivo la trae
    path: str


class RocTable(NamedTuple):
    """La curva ROC tal como la devuelve `metrics.roc_curve`."""

    fpr: np.ndarray
    tpr: np.ndarray
    thresholds: np.ndarray


# --------------------------------------------------------------------------
# Lectura y alineacion
# --------------------------------------------------------------------------


def read_band(path: str, nodata_to_nan: bool = True) -> RasterBand:
    """Lee la unica banda de un GeoTIFF como float64.

    Parameters
    ----------
    path:
        Ruta del GeoTIFF. Debe tener exactamente una banda.
    nodata_to_nan:
        Si True y el archivo declara un `nodata` numerico, esos pixeles pasan a
        NaN. Los mapas del proyecto ya usan NaN como nodata, asi que con ellos
        no cambia nada; existe para mapas de terceros con -9999.

    Returns
    -------
    RasterBand
        Datos, CRS, transform y descripcion de la banda.

    Raises
    ------
    FileNotFoundError
        Si el archivo no existe.
    ValueError
        Si el archivo trae mas de una banda: elegir la primera en silencio
        evaluaria quiza la banda equivocada.
    """
    ruta = Path(path)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el raster {ruta}.")

    with rasterio.open(ruta) as src:
        if src.count != 1:
            raise ValueError(
                f"{ruta} tiene {src.count} bandas; se espera un mapa de una sola "
                f"banda. Elegir una en silencio podria evaluar la equivocada."
            )
        datos = src.read(1).astype(np.float64)
        nodata = src.nodata
        descripcion = src.descriptions[0] if src.descriptions else None
        crs, transform = src.crs, src.transform

    if nodata_to_nan and nodata is not None and not math.isnan(nodata):
        datos[datos == nodata] = np.nan

    return RasterBand(datos, crs, transform, descripcion, str(ruta))


def check_alignment(a: RasterBand, b: RasterBand) -> None:
    """Aborta si los dos rasteres no comparten forma, CRS y transform.

    Lista **todas** las diferencias, no solo la primera: quien regenera un
    archivo para corregir la forma no deberia descubrir recien en la siguiente
    corrida que el CRS tambien difiere.

    Parameters
    ----------
    a, b:
        Las dos bandas a comparar, tipicamente el mapa y la verdad.

    Raises
    ------
    AlignmentError
        Con una linea por cada propiedad que difiere.
    """
    diferencias = []
    if a.data.shape != b.data.shape:
        diferencias.append(f"forma: {a.data.shape} vs {b.data.shape}")
    if a.crs != b.crs:
        diferencias.append(f"CRS: {a.crs} vs {b.crs}")
    if not a.transform.almost_equals(b.transform, precision=TOLERANCIA_TRANSFORM):
        diferencias.append(
            f"transform:\n      {tuple(a.transform)[:6]}\n"
            f"   vs {tuple(b.transform)[:6]}"
        )

    if diferencias:
        detalle = "\n".join(f"  - {d}" for d in diferencias)
        raise AlignmentError(
            f"{a.path} y {b.path} no estan en la misma grilla:\n{detalle}\n"
            f"No se reproyecta en silencio. Regenera los dos desde el mismo Scene "
            f"(scripts/run_pipeline.py y scripts/construir_verdad_terreno.py)."
        )


def decode_truth(truth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Traduce las clases de la verdad de terreno a (positivos, evaluables).

    Acepta la verdad tanto en uint8 como en float32: `write_geotiff` escribe
    siempre float32, asi que el `ground_truth.tif` del proyecto llega con las
    clases 0.0 / 1.0 / 255.0 y NaN como nodata.

    Parameters
    ----------
    truth:
        Raster de clases de `validation.geology`.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        `(positivos, evaluables)`, dos mascaras booleanas. `evaluables` es
        False en los ambiguos y en los NaN.

    Raises
    ------
    ValueError
        Si aparece un valor que no es ninguna de las tres clases. Un raster con
        valores 0-100 (una probabilidad, por ejemplo) pasado como verdad daria
        "positivo = 1" y "negativo = 0" sobre una fraccion arbitraria de
        pixeles, sin fallar.
    """
    truth = np.asarray(truth, dtype=np.float64)
    finitos = np.isfinite(truth)
    clases = (CLASE_POSITIVO, CLASE_NEGATIVO, CLASE_AMBIGUO)

    conocidos = np.isin(truth, clases) | ~finitos
    if not conocidos.all():
        raros = np.unique(truth[~conocidos])[:10]
        raise ValueError(
            f"La verdad de terreno trae valores fuera de las clases "
            f"{list(clases)} de validation.geology: {raros.tolist()}. "
            f"¿Es el archivo correcto?"
        )

    positivos = truth == CLASE_POSITIVO
    evaluables = finitos & (truth != CLASE_AMBIGUO)
    return positivos, evaluables


# --------------------------------------------------------------------------
# Direccion del puntaje
# --------------------------------------------------------------------------


def _direccion_de_detector(nombre: str) -> bool | None:
    """`higher_is_better` del detector registrado bajo `nombre`, o None.

    El import es local: `pipeline` arrastra preprocesamiento y visualizacion, y
    no tiene sentido pagar ese costo cuando la direccion llega por la CLI.
    """
    from mineralmap.pipeline import DETECTORS

    clase = DETECTORS.get(nombre)
    return None if clase is None else bool(clase.higher_is_better)


def _direccion_de_banda(descripcion: str | None) -> tuple[bool | None, str | None]:
    """Deduce la direccion de la descripcion de banda que escribe el pipeline.

    `pipeline.run_pipeline` describe la banda como
    ``"{algoritmo}_angle_rad_{mineral}"``, p. ej. ``"sam_angle_rad_kaolinite"``.
    Se reconoce el prefijo hasta el primer ``_`` contra el registro de
    detectores; cualquier otra descripcion no dice nada.
    """
    if not descripcion:
        return None, None
    nombre = descripcion.split("_", 1)[0]
    return _direccion_de_detector(nombre), nombre


def resolve_direction(
    declared: bool | None,
    band_description: str | None = None,
    config_path: str | None = None,
) -> tuple[bool, str, list[str]]:
    """Decide `higher_is_better` sin inventar un default.

    Orden: lo declarado en la CLI; si no, el `algorithm.name` del config; si
    no, la descripcion de banda del GeoTIFF. Si nada lo dice, aborta.

    Parameters
    ----------
    declared:
        True / False si la CLI lo declaro, None si no.
    band_description:
        Descripcion de la banda del mapa de puntaje.
    config_path:
        YAML del experimento, opcional.

    Returns
    -------
    tuple[bool, str, list[str]]
        (direccion, de donde salio, advertencias). Hay advertencia cuando lo
        declarado contradice lo que dicen los metadatos: se respeta lo
        declarado, pero se deja escrito, porque es exactamente el escenario de
        un AUC invertido.

    Raises
    ------
    ValueError
        Si no se declaro y no se puede deducir, o si el config y la banda se
        contradicen entre si.
    """
    advertencias: list[str] = []
    deducciones: list[tuple[bool, str]] = []

    if config_path:
        from mineralmap.config import load_config

        nombre = str(load_config(config_path).algorithm.get("name", ""))
        valor = _direccion_de_detector(nombre)
        if valor is None:
            raise ValueError(
                f"El config {config_path} declara algorithm.name='{nombre}', que "
                f"no esta registrado en pipeline.DETECTORS."
            )
        deducciones.append((valor, f"config {config_path} (algorithm.name={nombre})"))

    valor_banda, nombre_banda = _direccion_de_banda(band_description)
    if valor_banda is not None:
        deducciones.append(
            (valor_banda, f"banda del GeoTIFF '{band_description}' ({nombre_banda})")
        )

    if len({v for v, _ in deducciones}) > 1:
        raise ValueError(
            "El config y la banda del GeoTIFF dicen direcciones distintas: "
            + "; ".join(
                f"{fuente} -> higher_is_better={v}" for v, fuente in deducciones
            )
            + ". Declarala con --higher-is-better o --lower-is-better."
        )

    if declared is not None:
        for valor, fuente in deducciones:
            if valor != declared:
                advertencias.append(
                    f"Se declaro higher_is_better={declared} pero {fuente} dice "
                    f"{valor}. Se usa lo declarado; si fue un error, el AUC "
                    f"sale invertido (1 - AUC)."
                )
        return declared, "argumento de la CLI", advertencias

    if deducciones:
        return deducciones[0][0], deducciones[0][1], advertencias

    raise ValueError(
        "No se declaro la direccion del puntaje y no se pudo deducir: "
        f"la banda se describe como {band_description!r} y no se paso --config. "
        "Usa --higher-is-better (probabilidades, indices) o --lower-is-better "
        "(angulo de SAM). No hay default: un AUC con la direccion invertida es "
        "1 - AUC y no lanza ningun error."
    )


# --------------------------------------------------------------------------
# Parte A: evaluacion por pixel
# --------------------------------------------------------------------------


def _detectar(score: np.ndarray, umbral: float, higher_is_better: bool) -> np.ndarray:
    """Binariza el puntaje con la regla de `algorithms.base.Detector.detects`.

    No se instancia un `Detector` porque aca no hay uno: el mapa puede venir de
    cualquier fuente. La regla es la misma (`>=` o `<=` segun la direccion) y
    los NaN salen False por IEEE-754.
    """
    return score >= umbral if higher_is_better else score <= umbral


def _metricas_binarias(
    verdad: np.ndarray, deteccion: np.ndarray, validos: np.ndarray
) -> dict[str, Any]:
    """Todas las metricas de una mascara binaria, con `metrics.py`."""
    matriz = confusion_matrix(verdad, deteccion, valid=validos)
    pr = precision_recall(verdad, deteccion, valid=validos)
    return {
        "n_detected": matriz.tp + matriz.fp,
        "confusion": matriz._asdict(),
        "precision": pr.precision,
        "recall": pr.recall,
        "f1": f1_score(verdad, deteccion, valid=validos),
        "iou": iou_score(verdad, deteccion, valid=validos),
        "kappa": cohen_kappa(verdad, deteccion, valid=validos),
        "spatial_enrichment": spatial_enrichment(deteccion, verdad, valid=validos),
    }


def evaluate_pixels(
    score: np.ndarray,
    truth: np.ndarray,
    higher_is_better: bool,
    threshold: float | None = None,
    seed: int = 42,
) -> tuple[dict[str, Any], RocTable]:
    """Parte A: AUC del puntaje y, con umbral, metricas binarias contra la verdad.

    La mascara valida es "puntaje no NaN y verdad no ambigua". Todas las
    metricas salen de `validation.metrics`; esta funcion solo arma las mascaras.

    Linea base aleatoria. Con umbral, se construye una mascara de ruido con
    **exactamente** la misma cantidad de pixeles que la deteccion (con
    `spectral.indices.mask_by_positive_rate`, como el contraste E5 de
    `scripts/sweep_threshold.py`) y se le calculan las mismas metricas. Es lo
    que da escala a los numeros: con 1 % de positivos, un F1 de 0,03 puede ser
    mucho o nada segun lo que saque el azar. El AUC del azar se calcula sobre
    el mismo ruido usado como puntaje continuo, y deberia rondar 0,5.

    Parameters
    ----------
    score:
        Mapa de puntaje 2D con NaN en lo invalido.
    truth:
        Raster de clases (1 / 0 / 255) de la misma forma.
    higher_is_better:
        Direccion del puntaje.
    threshold:
        Umbral en las unidades del puntaje. None omite las metricas binarias y
        la linea base.
    seed:
        Semilla del ruido de la linea base. Fija y declarada en la salida: sin
        ella el veredicto "mejor que el azar" cambiaria entre corridas.

    Returns
    -------
    tuple[dict, RocTable]
        El dict de metricas (serializable a JSON tras `to_jsonable`) y la curva
        ROC completa.
    """
    positivos, evaluables = decode_truth(truth)
    validos = evaluables & np.isfinite(score)

    n_validos = int(np.count_nonzero(validos))
    n_pos = int(np.count_nonzero(positivos & validos))
    resultado: dict[str, Any] = {
        "counts": {
            "total": int(score.size),
            "valid": n_validos,
            "positive": n_pos,
            "negative": n_validos - n_pos,
            "score_nan": int(np.count_nonzero(~np.isfinite(score))),
            "truth_ambiguous_or_nodata": int(np.count_nonzero(~evaluables)),
        },
        "higher_is_better": higher_is_better,
        "auc": roc_auc(
            positivos, score, valid=validos, higher_is_better=higher_is_better
        ),
        "threshold": threshold,
        "seed": seed,
        "at_threshold": None,
        "random_baseline": None,
    }

    fpr, tpr, umbrales = roc_curve(
        positivos, score, valid=validos, higher_is_better=higher_is_better
    )
    roc = RocTable(fpr, tpr, umbrales)

    if threshold is None:
        return resultado, roc

    deteccion = _detectar(score, threshold, higher_is_better) & validos
    resultado["at_threshold"] = _metricas_binarias(positivos, deteccion, validos)

    n_detectados = int(np.count_nonzero(deteccion))
    ruido = np.random.default_rng(seed).random(score.shape)
    base: dict[str, Any] = {
        "auc": roc_auc(positivos, ruido, valid=validos, higher_is_better=True),
    }
    if n_detectados == 0:
        # Sin detecciones no hay tasa que igualar. Se dice en vez de inventarla.
        base["note"] = "sin detecciones al umbral: no hay tasa de positivos que igualar"
    else:
        tasa = n_detectados / n_validos
        azar = mask_by_positive_rate(ruido, tasa, valid=validos)
        base.update(positive_rate=tasa, **_metricas_binarias(positivos, azar, validos))
    resultado["random_baseline"] = base

    return resultado, roc


# --------------------------------------------------------------------------
# Parte B: puntos de porfidos
# --------------------------------------------------------------------------


def _columna(columnas: list[str], candidatas: tuple[str, ...], que: str) -> str:
    """Encuentra la columna de lat o lon sin distinguir mayusculas."""
    por_minuscula = {c.strip().lower(): c for c in columnas}
    for candidata in candidatas:
        if candidata in por_minuscula:
            return por_minuscula[candidata]
    raise ValueError(
        f"No encontre una columna de {que} en el CSV; columnas: {columnas}. "
        f"Nombres aceptados: {list(candidatas)}."
    )


def load_points_lonlat(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Lee puntos (lon, lat) en EPSG:4326 desde un CSV o un archivo vectorial.

    - **CSV**: columnas de latitud y longitud en grados decimales WGS84
      (nombres aceptados en `COLUMNAS_LAT` / `COLUMNAS_LON`).
    - **GeoJSON / GPKG / shapefile**: geometrias Point. Si el archivo declara
      otro CRS, se lleva a EPSG:4326; si no declara ninguno, se rechaza, por la
      misma razon que en `geology.load_geology_polygons`.

    Parameters
    ----------
    path:
        Ruta del archivo de puntos.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (lon, lat) en grados.

    Raises
    ------
    FileNotFoundError
        Si el archivo no existe.
    ValueError
        Si faltan columnas, hay geometrias que no son puntos, coordenadas no
        finitas o fuera de rango (tipico de lat/lon intercambiadas o de
        coordenadas UTM en un CSV que se declara en grados).
    """
    ruta = Path(path)
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo de puntos {ruta}.")

    if ruta.suffix.lower() == ".csv":
        import pandas as pd

        tabla = pd.read_csv(ruta)
        columnas = list(tabla.columns)
        lat = tabla[_columna(columnas, COLUMNAS_LAT, "latitud")].to_numpy(float)
        lon = tabla[_columna(columnas, COLUMNAS_LON, "longitud")].to_numpy(float)
    else:
        import geopandas as gpd

        gdf = gpd.read_file(ruta)
        if gdf.crs is None:
            raise ValueError(
                f"{ruta} no declara CRS; no se puede saber en que coordenadas "
                f"estan los puntos."
            )
        tipos = set(gdf.geometry.geom_type.dropna().unique())
        if tipos - {"Point"}:
            raise ValueError(
                f"{ruta} trae geometrias {sorted(tipos)}; se esperan solo Point."
            )
        gdf = gdf.to_crs("EPSG:4326")
        lon = gdf.geometry.x.to_numpy(float)
        lat = gdf.geometry.y.to_numpy(float)

    if not (np.isfinite(lon).all() and np.isfinite(lat).all()):
        raise ValueError(f"{ruta} trae coordenadas vacias o no numericas.")
    if (np.abs(lat) > 90).any() or (np.abs(lon) > 180).any():
        raise ValueError(
            f"{ruta} trae coordenadas fuera de rango para grados WGS84 "
            f"(lat en [-90, 90], lon en [-180, 180]). ¿Columnas intercambiadas "
            f"o coordenadas proyectadas?"
        )
    return lon, lat


def lonlat_to_rowcol(
    lon: np.ndarray, lat: np.ndarray, crs: CRS, transform: Affine
) -> np.ndarray:
    """Reproyecta puntos EPSG:4326 al CRS del raster y los lleva a fila/columna.

    La fila/columna es el `floor` de la coordenada de pixel, o sea el pixel que
    **contiene** al punto. Un `round` lo moveria al pixel vecino cada vez que
    cae en la mitad inferior derecha de su celda. Los puntos fuera del raster
    salen con indices fuera de rango, y `capture_rate` los cuenta aparte.

    Parameters
    ----------
    lon, lat:
        Coordenadas en grados WGS84.
    crs:
        CRS del raster destino.
    transform:
        Transform afin del raster destino.

    Returns
    -------
    np.ndarray
        Arreglo int64 (n, 2) de (fila, columna).
    """
    from rasterio.warp import transform as reproyectar

    if crs is None:
        raise ValueError("El raster no declara CRS: no se pueden ubicar los puntos.")

    xs, ys = reproyectar(CRS.from_epsg(4326), crs, list(lon), list(lat))
    xs, ys = np.asarray(xs), np.asarray(ys)

    # Coeficientes de la inversa escritos a mano en vez de `~transform * (x, y)`:
    # `affine` esta deprecando `*` en favor de `@`, y `@` no existe en las
    # versiones viejas que todavia trae algun entorno conda.
    inversa = ~transform
    columnas = inversa.a * xs + inversa.b * ys + inversa.c
    filas = inversa.d * xs + inversa.e * ys + inversa.f
    return np.column_stack([np.floor(filas), np.floor(columnas)]).astype(np.int64)


# --------------------------------------------------------------------------
# Parte C: bloques
# --------------------------------------------------------------------------


def block_size_px(crs: CRS, transform: Affine, block_km: float) -> tuple[int, int]:
    """Convierte un lado de bloque en km a (filas, columnas) de pixeles.

    Raises
    ------
    ValueError
        Si el CRS no es proyectado (en grados, 5 km no es un numero fijo de
        pixeles), si la grilla esta rotada, o si `block_km` no es positivo.
    """
    if block_km <= 0:
        raise ValueError(f"--block-km debe ser positivo; recibi {block_km}.")
    if crs is None or not crs.is_projected:
        raise ValueError(
            f"Los bloques en km necesitan un CRS proyectado; el raster esta en {crs}."
        )
    if transform.b != 0 or transform.d != 0:
        raise ValueError("La grilla esta rotada; los bloques en km no aplican.")

    _, a_metros = crs.linear_units_factor
    lado_m = block_km * 1000.0
    filas = max(1, round(lado_m / (abs(transform.e) * a_metros)))
    columnas = max(1, round(lado_m / (abs(transform.a) * a_metros)))
    return int(filas), int(columnas)


# --------------------------------------------------------------------------
# Orquestacion, salidas y reporte
# --------------------------------------------------------------------------


def git_commit() -> dict[str, Any] | None:
    """Commit de HEAD y si el arbol tiene cambios sin commitear, o None.

    El estado "sucio" importa tanto como el hash: un metrics.json con el hash
    de HEAD pero calculado con cambios locales no se puede reproducir desde ese
    commit.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        estado = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return {"sha": sha, "dirty": bool(estado.strip())}


def run_evaluation(
    score_path: str,
    truth_path: str | None = None,
    higher_is_better: bool | None = None,
    config_path: str | None = None,
    threshold: float | None = None,
    seed: int = 42,
    porphyries_path: str | None = None,
    top_fraction: float = 0.10,
    block_km: float | None = 5.0,
) -> tuple[dict[str, Any], RocTable | None]:
    """Corre las partes A, B y C que permitan los insumos recibidos.

    Parameters
    ----------
    score_path:
        GeoTIFF del mapa de puntaje.
    truth_path:
        GeoTIFF de clases de la verdad de terreno. None omite la Parte A y el
        AUC por bloque.
    higher_is_better:
        Direccion declarada; None intenta deducirla (`resolve_direction`).
    config_path:
        YAML del experimento, solo para deducir la direccion.
    threshold:
        Umbral para las metricas binarias. Requiere `truth_path`.
    seed:
        Semilla de la linea base aleatoria.
    porphyries_path:
        CSV o GeoJSON de puntos en EPSG:4326. None omite la Parte B.
    top_fraction:
        Fraccion top para la captura.
    block_km:
        Lado del bloque de la Parte C en km. None la omite.

    Returns
    -------
    tuple[dict, RocTable | None]
        El dict completo de resultados y la curva ROC (None sin verdad).

    Raises
    ------
    ValueError
        Sin verdad ni puntos (no hay nada que evaluar), umbral sin verdad,
        rasteres desalineados (`AlignmentError`) o direccion no deducible.
    FileNotFoundError
        Si falta algun archivo de entrada.
    """
    if truth_path is None and porphyries_path is None:
        raise ValueError(
            "Nada que evaluar: pasa --truth (Parte A), --porphyries (Parte B) o ambos."
        )
    if threshold is not None and truth_path is None:
        raise ValueError(
            "--threshold necesita --truth: las metricas binarias se calculan "
            "contra la verdad de terreno."
        )

    mapa = read_band(score_path)
    direccion, fuente, advertencias = resolve_direction(
        higher_is_better, mapa.description, config_path
    )

    resultado: dict[str, Any] = {
        "inputs": {
            "score": score_path,
            "score_band": mapa.description,
            "truth": truth_path,
            "porphyries": porphyries_path,
            "config": config_path,
        },
        "git": git_commit(),
        "grid": {
            "shape": list(mapa.data.shape),
            "crs": str(mapa.crs) if mapa.crs else None,
            "transform": list(tuple(mapa.transform)[:6]),
        },
        "higher_is_better": direccion,
        "direction_source": fuente,
        "warnings": advertencias,
        "threshold": threshold,
        "seed": seed,
        "pixel": None,
        "capture": None,
        "blocks": None,
    }

    roc = None
    positivos = evaluables = None
    if truth_path is not None:
        # La verdad no pasa por la conversion nodata -> NaN: el nodata de un
        # raster de clases puede ser 255 (que ya es "ambiguo") o 0, y en ese
        # caso convertirlo borraria todos los negativos.
        verdad = read_band(truth_path, nodata_to_nan=False)
        check_alignment(mapa, verdad)
        pixel, roc = evaluate_pixels(
            mapa.data, verdad.data, direccion, threshold=threshold, seed=seed
        )
        resultado["pixel"] = pixel
        positivos, evaluables = decode_truth(verdad.data)

    puntos = None
    if porphyries_path is not None:
        lon, lat = load_points_lonlat(porphyries_path)
        puntos = lonlat_to_rowcol(lon, lat, mapa.crs, mapa.transform)
        captura = capture_rate(
            mapa.data, puntos, top_fraction=top_fraction, higher_is_better=direccion
        )
        resultado["capture"] = captura._asdict()
        if mapa.crs is not None and mapa.crs.is_projected:
            _, a_metros = mapa.crs.linear_units_factor
            km2_por_pixel = abs(mapa.transform.a * mapa.transform.e) * a_metros**2 / 1e6
            resultado["capture"]["area_valid_km2"] = (
                captura.n_valid_pixels * km2_por_pixel
            )
            resultado["capture"]["area_top_km2"] = captura.n_top_pixels * km2_por_pixel

    if block_km is not None:
        lado = block_size_px(mapa.crs, mapa.transform, block_km)
        bloques = block_metrics(
            mapa.data,
            lado,
            direccion,
            y_true=positivos,
            truth_valid=evaluables,
            points_rc=puntos,
            top_fraction=top_fraction,
        )
        resumen: dict[str, Any] = {
            "block_km": block_km,
            "block_px": list(lado),
            "n_blocks": len(bloques),
        }
        if positivos is not None:
            resumen["auc"] = summarize([b.auc for b in bloques])._asdict()
        if puntos is not None:
            resumen["capture"] = summarize(
                [
                    b.capture.capture if b.capture is not None else np.nan
                    for b in bloques
                ]
            )._asdict()
        resumen["per_block"] = [
            {
                "row0": b.row0,
                "col0": b.col0,
                "n_rows": b.n_rows,
                "n_cols": b.n_cols,
                "n_valid": b.n_valid,
                "n_pos": b.n_pos,
                "n_neg": b.n_neg,
                "auc": b.auc,
                "capture": b.capture.capture if b.capture is not None else None,
                "capture_n_evaluated": (
                    b.capture.n_evaluated if b.capture is not None else None
                ),
            }
            for b in bloques
        ]
        resultado["blocks"] = resumen

    return resultado, roc


def to_jsonable(valor: Any) -> Any:
    """Convierte el resultado a algo que `json.dump(allow_nan=False)` acepte.

    NaN pasa a `null`: es "no definido", y `null` es lo que cualquier lector de
    JSON entiende asi. Los infinitos pasan a las cadenas "inf" / "-inf" y no a
    null, porque son resultados reales y distintos de "no definido" (p. ej. el
    enriquecimiento espacial con cero detecciones fuera de la zona). El
    `NaN` literal que escribe `json.dump` por defecto no es JSON valido y
    rompe a `jq` y a la mayoria de los lectores fuera de Python.
    """
    if isinstance(valor, dict):
        return {str(k): to_jsonable(v) for k, v in valor.items()}
    if isinstance(valor, list | tuple):
        return [to_jsonable(v) for v in valor]
    if isinstance(valor, np.generic):
        valor = valor.item()
    if isinstance(valor, float):
        if math.isnan(valor):
            return None
        if math.isinf(valor):
            return "inf" if valor > 0 else "-inf"
    return valor


def write_outputs(
    resultado: dict[str, Any], roc: RocTable | None, out_dir: str
) -> list[str]:
    """Escribe `metrics.json` y, si hay curva, `roc.csv`.

    Returns
    -------
    list[str]
        Rutas escritas.
    """
    destino = Path(out_dir)
    destino.mkdir(parents=True, exist_ok=True)

    ruta_json = destino / "metrics.json"
    with open(ruta_json, "w", encoding="utf-8") as salida:
        json.dump(
            to_jsonable(resultado),
            salida,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
    escritas = [str(ruta_json)]

    if roc is not None:
        ruta_csv = destino / "roc.csv"
        tabla = np.column_stack([roc.fpr, roc.tpr, roc.thresholds])
        # `%.8g` y no la repr completa: 17 digitos por celda triplican el peso
        # de un archivo que puede tener cientos de miles de filas. El primer
        # umbral es +-inf (el punto que no detecta nada) y sale como "inf".
        np.savetxt(
            ruta_csv,
            tabla,
            delimiter=",",
            fmt="%.8g",
            header="fpr,tpr,threshold",
            comments="",
        )
        escritas.append(str(ruta_csv))

    return escritas


def _f(valor: Any, decimales: int = 4) -> str:
    """Formatea un numero para la tabla; '-' si no esta definido."""
    if valor is None:
        return "-"
    if isinstance(valor, float):
        if math.isnan(valor):
            return "NaN"
        if math.isinf(valor):
            return "inf" if valor > 0 else "-inf"
        return f"{valor:.{decimales}f}"
    if isinstance(valor, int):
        return f"{valor:,}"
    return str(valor)


def format_report(resultado: dict[str, Any]) -> str:
    """Tabla corta y legible del resultado, para la consola."""
    lineas = ["=" * 66]
    entradas = resultado["inputs"]
    lineas.append(f"Puntaje   : {entradas['score']}  [{entradas['score_band']}]")
    if entradas["truth"]:
        lineas.append(f"Verdad    : {entradas['truth']}")
    if entradas["porphyries"]:
        lineas.append(f"Porfidos  : {entradas['porphyries']}")
    lineas.append(
        f"Direccion : higher_is_better={resultado['higher_is_better']} "
        f"(de: {resultado['direction_source']})"
    )
    for advertencia in resultado["warnings"]:
        lineas.append(f"[ADVERTENCIA] {advertencia}")

    pixel = resultado["pixel"]
    if pixel is not None:
        c = pixel["counts"]
        lineas.append(
            f"Pixeles   : {c['valid']:,} validos = {c['positive']:,} positivos + "
            f"{c['negative']:,} negativos  (de {c['total']:,}; "
            f"{c['truth_ambiguous_or_nodata']:,} ambiguos, {c['score_nan']:,} NaN)"
        )
        lineas.append("-" * 66)
        lineas.append(f"{'':<22}{'mapa':>14}{'azar':>14}")
        base = pixel["random_baseline"] or {}
        lineas.append(f"{'AUC':<22}{_f(pixel['auc']):>14}{_f(base.get('auc')):>14}")

        umbral = pixel["at_threshold"]
        if umbral is not None:
            regla = ">=" if resultado["higher_is_better"] else "<="
            lineas.append(f"-- umbral: puntaje {regla} {resultado['threshold']}")
            filas = (
                ("detectados", "n_detected"),
                ("precision", "precision"),
                ("recall", "recall"),
                ("F1", "f1"),
                ("IoU", "iou"),
                ("kappa", "kappa"),
                ("enriquecimiento", "spatial_enrichment"),
            )
            for etiqueta, clave in filas:
                lineas.append(
                    f"{etiqueta:<22}{_f(umbral[clave]):>14}{_f(base.get(clave)):>14}"
                )
            if "note" in base:
                lineas.append(f"  (azar: {base['note']})")
            lineas.append(f"  semilla del azar: {resultado['seed']}")

    captura = resultado["capture"]
    if captura is not None:
        lineas.append("-" * 66)
        lineas.append(
            f"Captura de porfidos (top {100 * captura['top_fraction']:.1f} % de "
            f"{captura['n_valid_pixels']:,} px validos)"
        )
        lineas.append(
            f"  puntos {captura['n_points']} = {captura['n_evaluated']} evaluados + "
            f"{captura['n_invalid']} sobre pixel invalido + "
            f"{captura['n_outside']} fuera de la grilla"
        )
        lineas.append(
            f"  captura {_f(captura['capture'])} ({captura['n_captured']}/"
            f"{captura['n_evaluated']}) | azar {_f(captura['chance'])} | "
            f"razon {_f(captura['lift'], 2)}x"
        )

    bloques = resultado["blocks"]
    if bloques is not None:
        lineas.append("-" * 66)
        lineas.append(
            f"Bloques de {bloques['block_km']} km ({bloques['block_px'][0]}x"
            f"{bloques['block_px'][1]} px, {bloques['n_blocks']} bloques)"
        )
        for clave, etiqueta in (("auc", "AUC"), ("capture", "captura")):
            if clave in bloques:
                s = bloques[clave]
                lineas.append(
                    f"  {etiqueta:<8} media {_f(s['mean'])} +- {_f(s['std'])} "
                    f"[{_f(s['min'])}, {_f(s['max'])}] en {s['n_defined']}/"
                    f"{s['n_blocks']} bloques definidos"
                )

    lineas.append("=" * 66)
    return "\n".join(lineas)
