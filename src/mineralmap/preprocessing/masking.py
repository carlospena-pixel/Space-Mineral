"""Mascara de nubes/sombra/agua derivada de la banda SCL de Sentinel-2 L2A."""

from __future__ import annotations

import numpy as np

# Clasificacion de escena (Scene Classification Layer) que produce Sen2Cor.
# Es una etiqueta por pixel, no una medida: nunca se interpola.
SCL_CLASSES: dict[int, str] = {
    0: "nodata",  # sin dato
    1: "saturado",  # saturado o defectuoso
    2: "sombra_topografica",  # sombra proyectada por el relieve (cast shadow)
    3: "sombra_de_nube",  # sombra proyectada por nubes
    4: "vegetacion",
    5: "suelo_desnudo",  # incluye roca y afloramientos
    6: "agua",
    7: "no_clasificado",
    8: "nube_prob_media",  # nube, probabilidad media
    9: "nube_prob_alta",  # nube, probabilidad alta
    10: "cirrus",  # cirrus fino
    11: "nieve_hielo",
}

# Clases que se descartan por defecto. Se conservan 4 (vegetacion),
# 5 (suelo desnudo) y 7 (no clasificado):
#   - 5 es justamente lo que interesa para mapeo mineral en desierto: el
#     suelo/roca expuesto es donde la firma del mineral llega al sensor.
#   - 4 no es un pixel invalido, solo poco informativo para un mineral; si
#     filtrarla o no es decision del algoritmo, no del preprocesamiento.
#   - 7 es la clase "no se": descartarla implicaria confiar mas en Sen2Cor de
#     lo que corresponde en un terreno arido, donde clasifica mal seguido.
# El agua (6) SI se descarta: su firma espectral no tiene nada que ver con la
# de un mineral y solo aporta falsos positivos.
DEFAULT_INVALID_CLASSES: list[int] = [0, 1, 2, 3, 6, 8, 9, 10, 11]


def build_cloud_mask(scl_band, classes_to_mask: list[int]) -> np.ndarray:
    """Construye la mascara de validez a partir de la banda SCL.

    Devuelve True donde el pixel es USABLE (no es la mascara de nubes, es su
    complemento). El nombre "cloud mask" viene del contrato original del
    proyecto; la convencion de `Scene.mask` es True = pixel valido, y esta
    funcion respeta esa convencion.

    Parameters
    ----------
    scl_band:
        Banda SCL (enteros 0..11), forma (alto, ancho).
    classes_to_mask:
        Codigos SCL que se consideran invalidos (ver DEFAULT_INVALID_CLASSES).
        Una lista vacia deja todo el raster como valido.

    Returns
    -------
    np.ndarray
        Mascara booleana de la misma forma que `scl_band`: True = valido.
    """
    scl = np.asarray(scl_band)
    return ~np.isin(scl, list(classes_to_mask))


def apply_mask(cube: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Aplica la mascara de validez a un cubo, poniendo NaN en lo invalido.

    El cubo que produce `preprocessing` se guarda SIN enmascarar: la validez
    vive en `Scene.mask` y quien decide aplicarla es el pipeline. Esta funcion
    es ese paso explicito.

    Parameters
    ----------
    cube:
        Cubo de reflectancia, forma (n_bandas, alto, ancho).
    mask:
        Mascara booleana, forma (alto, ancho), True = pixel valido.

    Returns
    -------
    np.ndarray
        Copia del cubo con NaN en todas las bandas de los pixeles invalidos.
        El cubo original no se modifica.

    Raises
    ------
    ValueError
        Si `cube` no es 3D o si la forma espacial de `mask` no calza con la
        del cubo.
    """
    cube = np.asarray(cube)
    mask = np.asarray(mask, dtype=bool)

    if cube.ndim != 3:
        raise ValueError(
            f"El cubo debe tener forma (n_bandas, alto, ancho); recibi "
            f"{cube.ndim} dimensiones con forma {cube.shape}."
        )

    if mask.shape != cube.shape[1:]:
        raise ValueError(
            f"La mascara {mask.shape} no calza con la forma espacial del cubo "
            f"{cube.shape[1:]} (cubo completo: {cube.shape})."
        )

    if np.issubdtype(cube.dtype, np.floating):
        salida = cube.copy()
    else:
        # Un cubo entero no puede albergar NaN: se promueve a float32, que es
        # el dtype con que viaja la reflectancia en todo el proyecto.
        salida = cube.astype(np.float32)

    salida[:, ~mask] = np.nan
    return salida


def mask_summary(scl_band, classes_to_mask: list[int]) -> dict[str, float]:
    """Resume la composicion de la banda SCL como porcentajes.

    Sirve de control de cordura del preprocesamiento: si un AOI que deberia
    ser desierto despejado aparece con 30 % de nubes, el problema esta en la
    lectura o en el recorte, no en el algoritmo.

    Parameters
    ----------
    scl_band:
        Banda SCL (enteros), forma (alto, ancho).
    classes_to_mask:
        Codigos SCL considerados invalidos.

    Returns
    -------
    dict[str, float]
        Una entrada ``"{codigo}_{nombre}"`` por cada clase presente con su
        porcentaje de pixeles, mas ``"pct_validos"`` con el porcentaje de
        pixeles usables. Los porcentajes por clase suman ~100; `pct_validos`
        es un agregado aparte y no entra en esa suma.
    """
    scl = np.asarray(scl_band)
    total = scl.size

    resumen: dict[str, float] = {}
    codigos, cuentas = np.unique(scl, return_counts=True)
    for codigo, cuenta in zip(codigos.tolist(), cuentas.tolist()):
        nombre = SCL_CLASSES.get(int(codigo), "desconocido")
        resumen[f"{int(codigo)}_{nombre}"] = 100.0 * cuenta / total

    resumen["pct_validos"] = float(
        100.0 * build_cloud_mask(scl, classes_to_mask).mean()
    )
    return resumen
