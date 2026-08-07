"""Graficos comparativos de firmas espectrales (referencia vs. pixel)."""

from __future__ import annotations

import numpy as np

from mineralmap.config import BAND_ORDER, BAND_WAVELENGTHS_NM, DEFAULT_PLATFORM

# Modos de normalizacion aceptados por plot_spectra.
NORMALIZATIONS = ("none", "l2", "max")

_ETIQUETA_Y = {
    "none": "Reflectancia",
    "l2": "Reflectancia normalizada (norma L2 = 1)",
    "max": "Reflectancia normalizada (maximo = 1)",
}


def _bandas_del_sensor(platform: str) -> list[str]:
    """Todas las bandas del sensor ordenadas por longitud de onda creciente."""
    tabla = BAND_WAVELENGTHS_NM[platform]
    return sorted(tabla, key=lambda banda: tabla[banda])


def normalize_signature(values: np.ndarray, mode: str = "l2") -> np.ndarray:
    """Normaliza una firma espectral segun `mode`, propagando los NaN.

    Parameters
    ----------
    values:
        Vector 1D de reflectancia. Puede traer NaN.
    mode:
        "none" devuelve el vector intacto; "l2" lo lleva a norma unitaria;
        "max" lo divide por su valor maximo.

    Returns
    -------
    np.ndarray
        Vector normalizado, del mismo largo. Las posiciones que eran NaN
        siguen siendo NaN: un NaN es "esta banda no se midio", y sustituirlo
        por 0 lo convierte en "esta banda midio reflectancia nula", que es un
        dato distinto y que ademas mueve el factor de normalizacion.

    Raises
    ------
    ValueError
        Si `mode` no es uno de NORMALIZATIONS, o si el vector no tiene ningun
        valor finito distinto de cero (no tiene direccion que normalizar, y el
        SAM tampoco podria calcular un angulo contra el).
    """
    if mode not in NORMALIZATIONS:
        raise ValueError(
            f"normalize='{mode}' no es valido; usa uno de {list(NORMALIZATIONS)}."
        )

    valores = np.asarray(values, dtype=float)
    if mode == "none":
        return valores

    # El factor se calcula sobre los valores finitos: si una banda no se midio,
    # no debe arrastrar toda la firma a NaN.
    if mode == "l2":
        factor = float(np.sqrt(np.nansum(valores**2)))
    else:
        finitos = valores[np.isfinite(valores)]
        factor = float(finitos.max()) if finitos.size else 0.0

    if not np.isfinite(factor) or factor == 0.0:
        raise ValueError(
            f"No se puede normalizar con mode='{mode}': el factor resulto "
            f"{factor}. La firma no tiene ningun valor finito distinto de cero."
        )

    return valores / factor


def plot_spectra(
    signatures: dict[str, np.ndarray],
    band_order: list[str] = BAND_ORDER,
    normalize: str = "l2",
    ax=None,
    title: str = "",
    platform: str = DEFAULT_PLATFORM,
):
    """Superpone firmas espectrales sobre un eje de longitud de onda.

    Tres decisiones de diseno, cada una porque la alternativa produce un
    grafico que se ve bien y enganya:

    **El eje x es la longitud de onda en nm, no el indice de banda.** El indice
    miente sobre las distancias: entre B8A (864 nm) y B11 (1610 nm) hay 745 nm,
    y entre B5 (704) y B6 (739) hay 35, pero en un eje por indice ambos saltos
    miden lo mismo. Con el indice, la pendiente de cualquier tramo del grafico
    no significa nada, y la pendiente es justo lo que se lee para reconocer un
    rasgo de absorcion.

    **`normalize="l2"` es el default.** El SAM compara direcciones, no
    magnitudes: es invariante al albedo por construccion. Graficar en norma
    unitaria es graficar exactamente lo que el algoritmo ve. Sin normalizar, la
    firma de laboratorio de la caolinita (reflectancia AREF) y un pixel real de
    la escena (reflectancia superficial) quedan separadas por un factor ~2.1 en
    esta escena, y el grafico sugiere un desalineamiento que no existe.

    **Hay hueco explicito donde el sensor no muestreo.** Entre dos bandas
    consecutivas de `band_order` que no son vecinas en el sensor se corta la
    linea. El caso concreto es B9 (945 nm) y B11 (1610 nm): B10 no existe en el
    producto L2A, y unirlas con una recta continua dibuja una interpolacion a
    lo largo de 665 nm donde no hay ni una sola medicion.

    Parameters
    ----------
    signatures:
        Nombre -> vector 1D de reflectancia, cada uno de largo
        `len(band_order)` y alineado posicionalmente con el.
    band_order:
        Bandas de los vectores, en orden. Por defecto BAND_ORDER.
    normalize:
        Uno de NORMALIZATIONS ("none", "l2", "max"). Ver `normalize_signature`.
    ax:
        Eje de matplotlib donde dibujar. Si es None se crea una figura nueva.
    title:
        Titulo del grafico.
    platform:
        "S2A" o "S2B", para resolver las longitudes de onda del eje x. Por
        defecto DEFAULT_PLATFORM. El parametro existe y no se deduce porque
        usar la tabla equivocada no falla: corre el centro de B12 casi 17 nm
        dentro del rasgo Al-OH de la caolinita.

    Returns
    -------
    matplotlib.axes.Axes
        El eje donde se dibujo, sea el recibido o el creado.

    Raises
    ------
    ValueError
        Si algun vector de `signatures` no tiene largo `len(band_order)`, o si
        `normalize` no es un modo valido.
    """
    import matplotlib.pyplot as plt

    tabla = BAND_WAVELENGTHS_NM[platform]
    faltantes = [banda for banda in band_order if banda not in tabla]
    if faltantes:
        raise ValueError(
            f"No hay longitud de onda registrada para {faltantes} en {platform}."
        )

    lambdas = np.array([tabla[banda] for banda in band_order], dtype=float)

    for nombre, valores in signatures.items():
        vector = np.asarray(valores, dtype=float)
        if vector.shape != (len(band_order),):
            raise ValueError(
                f"La firma '{nombre}' tiene forma {vector.shape}; se esperaba "
                f"({len(band_order)},), el largo de band_order. Un vector de "
                f"otro largo significa que la firma y las bandas no son la "
                f"misma cosa, y superponerlas seria comparar bandas distintas."
            )

    if ax is None:
        _fig, ax = plt.subplots(figsize=(9, 5))

    for nombre, valores in signatures.items():
        vector = normalize_signature(np.asarray(valores, dtype=float), normalize)
        color = None
        for inicio, fin in _tramos_contiguos(band_order, platform):
            (linea,) = ax.plot(
                lambdas[inicio:fin],
                vector[inicio:fin],
                marker="o",
                markersize=4,
                color=color,
                # Solo el primer tramo aporta a la leyenda; si no, cada firma
                # apareceria tantas veces como huecos tenga el eje.
                label=nombre if color is None else "_nolegend_",
            )
            color = linea.get_color()

    ax.set_xlabel("Longitud de onda (nm)")
    ax.set_ylabel(_ETIQUETA_Y[normalize])
    if title:
        ax.set_title(title)
    ax.grid(alpha=0.3)
    ax.legend()

    return ax


def _tramos_contiguos(band_order: list[str], platform: str) -> list[tuple[int, int]]:
    """Parte `band_order` en tramos de bandas vecinas en el sensor.

    Devuelve pares (inicio, fin) de indices, con `fin` exclusivo, para usar como
    rebanadas. Dos bandas consecutivas de `band_order` pertenecen al mismo tramo
    solo si tambien son consecutivas en el sensor completo; si entre ellas hay
    alguna banda que el cubo no trae, el tramo se corta ahi.
    """
    posicion = {banda: i for i, banda in enumerate(_bandas_del_sensor(platform))}

    tramos: list[tuple[int, int]] = []
    inicio = 0
    for i in range(1, len(band_order)):
        if posicion[band_order[i]] - posicion[band_order[i - 1]] > 1:
            tramos.append((inicio, i))
            inicio = i
    tramos.append((inicio, len(band_order)))

    return tramos
