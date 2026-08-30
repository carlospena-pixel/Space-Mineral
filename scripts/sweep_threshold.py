"""CLI: barrido fino del umbral de angulo y contraste contra lineas base.

Que produce, y en que se diferencia del barrido que ya imprime el pipeline.
`pipeline.THRESHOLD_SWEEP` son cinco umbrales fijos que acompanan al resumen de
una corrida: sirven para que un resultado de cero detecciones no se confunda con
un error de calculo. Este script es la otra cosa: barre el umbral sobre un rango
derivado del **propio mapa** --de su minimo a su mediana-- y produce la tabla de
validacion del hito, con las metricas de la Semana 4. No importa ni amplia esa
constante, y no toca `pipeline.py`.

Que se puede medir hoy y que no. Sin verdad de terreno no existen E3
(enriquecimiento espacial) ni E4 (F1/IoU/AUC/kappa contra verdad): son las dos
cosas que necesitan una capa que diga donde hay alteracion, y esa capa es Track
A. Lo que si se puede medir sin ella es E5, el contraste con lineas base: cuanto
coincide la deteccion de SAM con el clay ratio, y cuanto coincide con el clay
ratio una mascara aleatoria de la misma tasa de positivos. **Esa comparacion es
la unica afirmacion defendible sin verdad de terreno**, y el script la escribe
con esas palabras: SAM coincide con el clay ratio mas, igual o menos que el azar.

El script no regenera nada. El `Scene` y el GeoTIFF de angulos son minutos de
lectura del `.SAFE`; si faltan, aborta diciendo el comando exacto que hay que
correr.

Uso (desde la raiz del repo):
    python scripts/sweep_threshold.py --config configs/tamarugal_kaolinite.yaml
    python scripts/sweep_threshold.py --config configs/x.yaml --truth verdad.tif
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from mineralmap.algorithms.base import Detector
from mineralmap.config import Config, load_config
from mineralmap.io.raster_io import load_scene
from mineralmap.pipeline import DETECTORS
from mineralmap.spectral.indices import clay_ratio, mask_by_positive_rate
from mineralmap.validation.metrics import (
    agreement,
    cohen_kappa,
    f1_score,
    iou_score,
    precision_recall,
    roc_auc,
    spatial_enrichment,
)

# Numero de umbrales del barrido, del minimo del mapa a su mediana. Es un
# recuento y no un paso absoluto en radianes a proposito: el rango util depende
# de la escena, y un paso fijo daria tres filas en un mapa concentrado y
# doscientas en uno disperso. El paso efectivo se imprime en la salida.
PASOS_DEL_BARRIDO = 25

# Semilla de la linea base aleatoria. Fija y declarada en la salida: sin ella la
# comparacion "SAM contra el azar" cambiaria de veredicto entre corridas y no se
# podria citar en ningun documento.
SEMILLA_BASELINE = 20260830

# Rutas por defecto, las mismas que usa el pipeline cuando el config no las
# declara (`pipeline.DEFAULT_SCENE_CACHE`, `DEFAULT_MAPS_DIR`). Se repiten aca
# en vez de importarlas para no acoplar este script a un modulo del Track A.
CACHE_SCENE_POR_DEFECTO = "data/interim/scene.npz"
DIR_MAPAS_POR_DEFECTO = "outputs/maps/"
NOMBRE_MAPA_POR_DEFECTO = "score_map.tif"

DIR_TABLAS_POR_DEFECTO = "outputs/tables/"

# Columnas de la tabla. Las cinco ultimas solo se llenan con verdad de terreno;
# sin ella quedan vacias, que no es lo mismo que un 0 (ver `_fila_del_barrido`).
COLUMNAS = (
    "umbral_rad",
    "pixeles",
    "pct_aoi_valido",
    "precision",
    "recall",
    "f1",
    "iou",
    "kappa",
)


def _abortar(mensaje: str) -> None:
    """Imprime el motivo y sale con codigo 1, como hace `run_pipeline.py`."""
    print(f"[ABORTADO] {mensaje}")
    sys.exit(1)


def _rutas_de_entrada(config: Config) -> tuple[str, str]:
    """Resuelve donde deberian estar el cache del Scene y el mapa de angulos.

    Los dos salen del config y no de constantes locales, para que apuntar el
    experimento a otra salida no exija editar este script.

    Parameters
    ----------
    config:
        Config del experimento, ya cargado.

    Returns
    -------
    tuple[str, str]
        (ruta del .npz del Scene, ruta del GeoTIFF de angulos).
    """
    ruta_scene = str(config.preprocessing.get("scene_cache", CACHE_SCENE_POR_DEFECTO))
    ruta_mapa = os.path.join(
        config.output.get("maps_dir", DIR_MAPAS_POR_DEFECTO),
        config.output.get("angle_map", NOMBRE_MAPA_POR_DEFECTO),
    )
    return ruta_scene, ruta_mapa


def _leer_mapa(ruta: str, forma_esperada: tuple[int, int]) -> np.ndarray:
    """Lee la banda 1 del GeoTIFF y comprueba que calza con la forma del Scene.

    Sin esta comprobacion, un mapa calculado sobre otra ventana produce una
    tabla de metricas impecable sobre el terreno equivocado: los conteos salen,
    los porcentajes salen, y nada dice que el angulo del pixel (0, 0) no
    corresponde al pixel (0, 0) del cubo. Es el mismo modo de falla que
    `io.raster_io.write_geotiff` evita del lado de la escritura.

    Parameters
    ----------
    ruta:
        GeoTIFF del mapa de angulos.
    forma_esperada:
        Forma espacial (alto, ancho) del Scene.

    Returns
    -------
    np.ndarray
        Mapa 2D en float64, con NaN en los pixeles sin dato.
    """
    with rasterio.open(ruta) as src:
        mapa = src.read(1).astype(np.float64)

    if mapa.shape != forma_esperada:
        _abortar(
            f"El mapa {ruta} tiene forma {mapa.shape} y el Scene "
            f"{forma_esperada}. Son de ventanas distintas: las metricas "
            f"saldrian igual, calculadas sobre el terreno equivocado. "
            f"Regenera el mapa con el mismo config."
        )

    return mapa


def _umbrales_del_barrido(
    mapa: np.ndarray, higher_is_better: bool
) -> tuple[np.ndarray, float]:
    """Umbrales del extremo mas selectivo del mapa hasta su mediana.

    El rango sale del propio mapa y no de cinco numeros fijos porque el umbral
    util depende de la escena: un barrido que empieza mas alla del extremo
    reporta ceros y uno que termina antes de la mediana no muestra donde
    empieza a detectar masivamente. La mediana es el techo natural: pasada
    ella se estaria marcando mas de la mitad del AOI, que ya no es una
    deteccion de nada.

    De que extremo se parte lo decide la direccion declarada por el detector.
    Con un puntaje donde menor es mejor --el angulo de SAM-- el barrido va del
    minimo hacia la mediana; con uno donde mayor es mejor, del maximo hacia la
    mediana. Fijar el minimo para los dos casos daria, en un detector de
    probabilidad, un barrido que arranca marcando el AOI entero y termina
    marcando la mitad: una tabla monotona sin nada que elegir.

    Parameters
    ----------
    mapa:
        Mapa de puntaje con NaN en lo invalido.
    higher_is_better:
        Direccion del puntaje, tal como la declara `Detector.higher_is_better`.

    Returns
    -------
    tuple[np.ndarray, float]
        (umbrales, paso efectivo en las unidades del puntaje, siempre positivo).
    """
    extremo = float(np.nanmax(mapa) if higher_is_better else np.nanmin(mapa))
    mediana = float(np.nanmedian(mapa))

    umbrales = np.linspace(extremo, mediana, PASOS_DEL_BARRIDO)
    paso = abs(mediana - extremo) / (PASOS_DEL_BARRIDO - 1)
    return umbrales, paso


def _fila_del_barrido(
    umbral: float,
    mapa: np.ndarray,
    validos: np.ndarray,
    verdad: np.ndarray | None,
    detector: Detector,
) -> dict[str, Any]:
    """Metricas de un umbral. Las de E4 quedan vacias si no hay verdad.

    Los campos sin verdad de terreno se dejan como cadena vacia y no como 0 ni
    como None: un 0 en la columna F1 se lee como "el detector no acerto nada",
    que es una medicion, cuando lo que pasa es que no hubo con que medir.
    """
    # `detects()` y no un `<=` a mano: el detector es el que sabe en que
    # direccion apunta su puntaje. Comparar a mano es exactamente el bug que ese
    # metodo existe para evitar --un detector con higher_is_better=True daria
    # cero detecciones bajo todos los umbrales sin lanzar nada--.
    detectado = detector.detects(mapa, umbral) & validos
    n_detectado = int(np.count_nonzero(detectado))
    n_validos = int(np.count_nonzero(validos))

    fila: dict[str, Any] = {
        "umbral_rad": umbral,
        "pixeles": n_detectado,
        "pct_aoi_valido": 100.0 * n_detectado / n_validos if n_validos else 0.0,
        "precision": "",
        "recall": "",
        "f1": "",
        "iou": "",
        "kappa": "",
    }

    if verdad is not None:
        pr = precision_recall(verdad, detectado, valid=validos)
        fila.update(
            precision=pr.precision,
            recall=pr.recall,
            f1=f1_score(verdad, detectado, valid=validos),
            iou=iou_score(verdad, detectado, valid=validos),
            kappa=cohen_kappa(verdad, detectado, valid=validos),
        )

    return fila


def _escribir_csv(filas: list[dict[str, Any]], ruta: str) -> None:
    """Escribe la tabla del barrido como CSV, creando el directorio si falta.

    Los flotantes se formatean a 6 decimales en vez de dejar la repr de Python:
    una columna de umbrales con 17 digitos significativos es ilegible y no
    aporta precision real sobre un angulo medido en una escena.
    """
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)

    with open(ruta, "w", encoding="utf-8", newline="") as salida:
        escritor = csv.DictWriter(salida, fieldnames=COLUMNAS)
        escritor.writeheader()
        for fila in filas:
            escritor.writerow(
                {
                    clave: (f"{valor:.6f}" if isinstance(valor, float) else valor)
                    for clave, valor in fila.items()
                }
            )


def _imprimir_barrido(
    filas: list[dict[str, Any]], paso: float, con_verdad: bool
) -> None:
    """Imprime la tabla del barrido."""
    print(f"\nBarrido de umbral (paso {paso:.5f} rad, {len(filas)} puntos)")
    if con_verdad:
        cabecera = (
            f"{'umbral':>9}  {'pixeles':>10}  {'% AOI':>8}  {'prec':>7}  "
            f"{'recall':>7}  {'F1':>7}  {'IoU':>7}  {'kappa':>7}"
        )
    else:
        cabecera = f"{'umbral':>9}  {'pixeles':>10}  {'% AOI':>8}"
    print(cabecera)
    print("-" * len(cabecera))

    for fila in filas:
        linea = (
            f"{fila['umbral_rad']:>9.4f}  {fila['pixeles']:>10,}  "
            f"{fila['pct_aoi_valido']:>7.3f} %"
        )
        if con_verdad:
            for clave in ("precision", "recall", "f1", "iou", "kappa"):
                valor = fila[clave]
                linea += f"  {valor:>7.4f}" if isinstance(valor, float) else "      - "
        print(linea)


def _contrastar_con_lineas_base(
    mascara_sam: np.ndarray,
    mapa_clay: np.ndarray,
    validos: np.ndarray,
    tasa: float,
) -> None:
    """E5: acuerdo de SAM con el clay ratio, contra el acuerdo del azar.

    Las tres mascaras se construyen a la **misma tasa de positivos**. Comparar
    dos mascaras de tamanos muy distintos haria que el IoU midiera la diferencia
    de tamano y no el acuerdo espacial (ver `spectral.indices`).

    La linea base aleatoria no es decorativa: es la que le da escala al numero.
    Un IoU de 0,02 entre SAM y el clay ratio no significa nada por si solo; lo
    que significa algo es si el azar, a la misma tasa, saca 0,0001 o saca 0,02.
    """
    mascara_clay = mask_by_positive_rate(
        mapa_clay, tasa, valid=validos, higher_is_better=True
    )

    # La linea base se arma con la misma funcion que la del clay ratio, sobre un
    # mapa de ruido: garantiza exactamente la misma cantidad de pixeles marcados
    # que las otras dos, que es la propiedad que hace comparables los tres IoU.
    ruido = np.random.default_rng(SEMILLA_BASELINE).random(mapa_clay.shape)
    mascara_azar = mask_by_positive_rate(ruido, tasa, valid=validos)

    sam_vs_clay = agreement(mascara_sam, mascara_clay, valid=validos)
    azar_vs_clay = agreement(mascara_azar, mascara_clay, valid=validos)

    print("\nE5 - Contraste con lineas base (medible sin verdad de terreno)")
    print(
        f"  Tasa de positivos comun : {tasa:.3e}  "
        f"({100.0 * tasa:.4f} % del AOI valido)"
    )
    print(f"  Semilla del azar        : {SEMILLA_BASELINE}")
    print(
        f"  Pixeles marcados        : SAM {sam_vs_clay.n_a:,} | "
        f"clay ratio {sam_vs_clay.n_b:,} | azar {azar_vs_clay.n_a:,}"
    )
    print(
        f"  SAM  vs clay ratio      : IoU {sam_vs_clay.iou:.6f} | "
        f"kappa {sam_vs_clay.kappa:.6f} | {sam_vs_clay.n_ambas:,} px en comun"
    )
    print(
        f"  azar vs clay ratio      : IoU {azar_vs_clay.iou:.6f} | "
        f"kappa {azar_vs_clay.kappa:.6f} | {azar_vs_clay.n_ambas:,} px en comun"
    )

    # El veredicto se redacta con las palabras que la evidencia sostiene. Sin
    # verdad de terreno, "SAM coincide con el clay ratio mas que el azar" es
    # todo lo que se puede afirmar: no dice que SAM tenga razon, dice que los
    # dos criterios no son independientes.
    if sam_vs_clay.n_ambas > azar_vs_clay.n_ambas:
        veredicto = "MAS que el azar"
    elif sam_vs_clay.n_ambas == azar_vs_clay.n_ambas:
        veredicto = "IGUAL que el azar"
    else:
        veredicto = "MENOS que el azar"
    print(f"\n  Veredicto: SAM coincide con el clay ratio {veredicto}.")
    print(
        "  No dice que SAM detecte caolinita: el clay ratio no es verdad de\n"
        "  terreno, es una segunda opinion sobre las mismas dos bandas de la\n"
        "  misma imagen, y los dos criterios pueden equivocarse juntos."
    )


def _evaluar_contra_verdad(
    mapa: np.ndarray,
    mascara_sam: np.ndarray,
    validos: np.ndarray,
    verdad: np.ndarray,
    detector: Detector,
) -> None:
    """E3 y E4 sobre la escena: solo se llama si llego una capa de verdad."""
    print("\nE4 - Metricas contra verdad de terreno (umbral del config)")
    pr = precision_recall(verdad, mascara_sam, valid=validos)
    print(f"  precision : {pr.precision:.6f}")
    print(f"  recall    : {pr.recall:.6f}")
    print(f"  F1        : {f1_score(verdad, mascara_sam, valid=validos):.6f}")
    print(f"  IoU       : {iou_score(verdad, mascara_sam, valid=validos):.6f}")
    print(f"  kappa     : {cohen_kappa(verdad, mascara_sam, valid=validos):.6f}")

    # La direccion no se supone: se la pide al detector. `metrics.roc_auc` no
    # conoce el proyecto y su default es la convencion estandar (mayor es mas
    # evidencia); con el angulo de SAM, omitirla devuelve 1 - AUC sin lanzar
    # nada, o sea 0,18 donde deberia decir 0,82.
    auc = roc_auc(
        verdad, mapa, valid=validos, higher_is_better=detector.higher_is_better
    )
    print(
        f"  AUC       : {auc:.6f}  "
        f"(direccion declarada: higher_is_better={detector.higher_is_better})"
    )

    print("\nE3 - Enriquecimiento espacial")
    razon = spatial_enrichment(mascara_sam, verdad, valid=validos)
    print(f"  Razon dentro/fuera : {razon:.4f}")
    print(
        "  1 = ninguna preferencia espacial; > 1 = las detecciones se concentran\n"
        "  en las zonas documentadas."
    )


def _parsear_argumentos() -> argparse.Namespace:
    """Argumentos de la CLI. El config es obligatorio y la verdad opcional."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        required=True,
        help="Ruta al YAML de configuracion del experimento",
    )
    parser.add_argument(
        "--truth",
        default=None,
        help=(
            "GeoTIFF booleano de verdad de terreno en la grilla del Scene. "
            "Opcional: sin el, E3 y E4 quedan sin calcular y se dice cuales."
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=DIR_TABLAS_POR_DEFECTO,
        help="Directorio donde escribir el CSV (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    """Carga los insumos, corre el barrido y el contraste, y escribe la tabla."""
    args = _parsear_argumentos()
    config = load_config(args.config)

    ruta_scene, ruta_mapa = _rutas_de_entrada(config)

    # Los dos insumos se comprueban antes de leer nada, y el mensaje dice el
    # comando exacto: regenerarlos son minutos de lectura del .SAFE y no es
    # trabajo de este script hacerlo por su cuenta.
    for ruta, que in ((ruta_scene, "el cache del Scene"), (ruta_mapa, "el mapa")):
        if not os.path.exists(ruta):
            _abortar(
                f"No existe {que} en {ruta}. Generalo con:\n"
                f"    python scripts/run_pipeline.py --config {args.config}"
            )

    # El detector sale del registro del pipeline y no se instancia SAM a mano:
    # es el mismo mecanismo que usa `run_pipeline`, asi que el barrido mide el
    # mismo algoritmo que produjo el mapa. Solo se lee `DETECTORS`; este script
    # no modifica nada de `pipeline.py`.
    nombre_algoritmo = str(config.algorithm.get("name", ""))
    if nombre_algoritmo not in DETECTORS:
        _abortar(
            f"El algoritmo '{nombre_algoritmo}' del config no esta registrado; "
            f"los disponibles son {sorted(DETECTORS)}."
        )
    detector = DETECTORS[nombre_algoritmo]()

    scene = load_scene(ruta_scene)
    mapa = _leer_mapa(ruta_mapa, tuple(scene.cube.shape[1:]))

    # La validez combina las dos fuentes: la mascara del Scene (nubes, agua) y
    # los NaN del propio mapa (norma cero, o cualquier pixel que el detector no
    # pudo puntuar). Quedarse solo con `scene.mask` metaria NaN en los conteos.
    validos = scene.mask & np.isfinite(mapa)
    n_validos = int(np.count_nonzero(validos))

    verdad = None
    if args.truth:
        if not os.path.exists(args.truth):
            _abortar(f"No existe la verdad de terreno en {args.truth}.")
        verdad = _leer_mapa(args.truth, tuple(scene.cube.shape[1:])) > 0

    umbral_config = float(
        config.algorithm.get("params", {}).get("angle_threshold_rad", float("nan"))
    )
    mascara_sam = detector.detects(mapa, umbral_config) & validos
    n_sam = int(np.count_nonzero(mascara_sam))

    print("=" * 72)
    print(f"Mineral objetivo   : {config.mineral.get('target')}")
    print(f"Mapa               : {ruta_mapa}")
    print(f"Scene              : {ruta_scene}  {tuple(scene.cube.shape)}")
    print(f"Pixeles validos    : {n_validos:,}")
    print(
        f"Angulo (rad)       : min {np.nanmin(mapa):.4f} | "
        f"mediana {np.nanmedian(mapa):.4f} | max {np.nanmax(mapa):.4f}"
    )
    print(
        f"Umbral del config  : {umbral_config} rad -> {n_sam:,} px "
        f"({100.0 * n_sam / n_validos:.4f} % del AOI valido)"
    )
    print("=" * 72)

    umbrales, paso = _umbrales_del_barrido(mapa, detector.higher_is_better)
    filas = [_fila_del_barrido(u, mapa, validos, verdad, detector) for u in umbrales]
    _imprimir_barrido(filas, paso, con_verdad=verdad is not None)

    ruta_csv = os.path.join(args.out_dir, "sweep_threshold.csv")
    _escribir_csv(filas, ruta_csv)
    print(f"\nTabla escrita en {ruta_csv}")

    # E5 necesita una tasa de positivos con la cual construir las otras dos
    # mascaras. Con cero detecciones no hay tasa que igualar, y el contraste no
    # se puede montar: se dice, en vez de inventar una tasa.
    if n_sam == 0:
        print(
            "\nE5 - SIN CALCULAR: el umbral del config no deja ninguna deteccion,\n"
            "  asi que no hay tasa de positivos con la cual construir la mascara\n"
            "  del clay ratio ni la del azar a la misma escala."
        )
    else:
        # El clay ratio se calcula sobre el cubo crudo y se enmascara despues.
        # Enmascarar el cubo antes costaria una copia de las 12 bandas para un
        # indice que solo lee dos.
        mapa_clay = clay_ratio(scene.cube, list(scene.band_names))
        mapa_clay = np.where(validos, mapa_clay, np.nan)
        _contrastar_con_lineas_base(mascara_sam, mapa_clay, validos, n_sam / n_validos)

    if verdad is not None:
        _evaluar_contra_verdad(mapa, mascara_sam, validos, verdad, detector)
    else:
        print(
            "\nE3 y E4 - SIN CALCULAR, BLOQUEADO POR TRACK A.\n"
            "  No se paso --truth y no hay ninguna capa de verdad de terreno en\n"
            "  el repositorio (data/external/ solo tiene la firma USGS de\n"
            "  caolinita). Sin ella quedan sin medir:\n"
            "    E4 : precision, recall, F1, IoU, kappa y AUC contra verdad.\n"
            "    E3 : enriquecimiento espacial en zonas de alteracion.\n"
            "  Las columnas correspondientes del CSV quedan vacias a proposito:\n"
            "  un 0 se leeria como una medicion que dio cero."
        )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, rasterio.errors.RasterioIOError) as e:
        _abortar(str(e))
