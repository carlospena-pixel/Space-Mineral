"""Heatmaps georreferenciados y overlays sobre la escena base."""

from __future__ import annotations

import numpy as np
from rasterio.transform import array_bounds

from mineralmap.io.raster_io import Scene
from mineralmap.preprocessing.masking import SCL_CLASSES

# Percentiles del realce de contraste. Una escena de desierto ocupa una franja
# estrecha del rango [0,1], asi que mostrarla sin estirar la deja casi negra.
P_LOW_DEFAULT = 2
P_HIGH_DEFAULT = 98

# Bandas del compuesto en color verdadero, en orden R, G, B.
TRUE_COLOR_BANDS = ("B4", "B3", "B2")

# Color por clase SCL, siguiendo la paleta con que Sen2Cor publica la Scene
# Classification: quien haya visto la clasificacion en el visor de Copernicus
# reconoce la figura sin leer la leyenda.
#
# El color se fija POR CODIGO, no por un colormap. Con un colormap continuo,
# `imshow` escala al rango presente en el recorte: la misma clase saldria de un
# color en este AOI y de otro en el de al lado, y la leyenda afirmaria lo
# contrario sin que nada falle.
SCL_COLORS: dict[int, str] = {
    0: "#000000",  # nodata
    1: "#ff0000",  # saturado
    2: "#2f2f2f",  # sombra topografica
    3: "#643200",  # sombra de nube
    4: "#00a000",  # vegetacion
    5: "#ffe65a",  # suelo desnudo
    6: "#0000ff",  # agua
    7: "#808080",  # no clasificado
    8: "#c0c0c0",  # nube prob. media
    9: "#ffffff",  # nube prob. alta
    10: "#64c8ff",  # cirrus
    11: "#ff96ff",  # nieve/hielo
}

# Codigo fuera de SCL_CLASSES: se pinta y se rotula como "desconocido" en vez
# de reventar o de confundirse con una clase declarada. Un SCL con codigos
# inesperados es un producto que hay que mirar, no un motivo para no ver nada.
UNKNOWN_SCL_COLOR = "#ff00ff"


def percentile_stretch(
    band: np.ndarray, p_low: int = P_LOW_DEFAULT, p_high: int = P_HIGH_DEFAULT
) -> np.ndarray:
    """Recorta una banda a sus percentiles [p_low, p_high] y la reescala a [0,1].

    Los percentiles se calculan ignorando los NaN. Es lo que permite realzar un
    cubo ya enmascarado: con `np.percentile`, un solo pixel invalido devuelve
    NaN como percentil y la imagen entera sale negra, sin ningun error de por
    medio.

    Parameters
    ----------
    band:
        Capa 2D de reflectancia. Puede traer NaN.
    p_low, p_high:
        Percentiles inferior y superior del recorte.

    Returns
    -------
    np.ndarray
        Capa reescalada a [0,1], con los NaN preservados. Si la banda es
        constante (o entera NaN) devuelve ceros: no hay contraste que estirar.
    """
    capa = np.asarray(band, dtype=float)

    if not np.any(np.isfinite(capa)):
        return np.zeros_like(capa)

    lo, hi = np.nanpercentile(capa, (p_low, p_high))
    if hi <= lo:
        return np.zeros_like(capa)

    return np.clip((capa - lo) / (hi - lo), 0, 1)


def rgb_composite(
    scene: Scene,
    bands: tuple[str, str, str] = TRUE_COLOR_BANDS,
    p_low: int = P_LOW_DEFAULT,
    p_high: int = P_HIGH_DEFAULT,
) -> np.ndarray:
    """Arma un compuesto RGB del AOI con realce por percentiles banda a banda.

    Cada banda se estira por separado: es un balance de blancos implicito, y sin
    el, el compuesto de una escena arida sale con dominante amarilla porque B4
    es sistematicamente mas brillante que B2 sobre suelo desnudo.

    Las bandas se buscan por nombre y no por indice. Es la unica capa del
    proyecto que lo hace (ver `docs/es/decisiones_tecnicas.md`, seccion 1.1):
    el resto trabaja posicionalmente, pero un compuesto en color tiene que
    saber cual banda es el rojo.

    Parameters
    ----------
    scene:
        Scene con el cubo y sus `band_names`. Sirve tanto el cubo crudo como
        uno ya enmascarado con `apply_mask`.
    bands:
        Nombres canonicos de las bandas a usar como R, G y B.
    p_low, p_high:
        Percentiles del realce, pasados a `percentile_stretch`.

    Returns
    -------
    np.ndarray
        Arreglo (alto, ancho, 3) en [0,1], listo para `imshow`.

    Raises
    ------
    ValueError
        Si alguna de las bandas pedidas no esta en el Scene.
    """
    faltantes = [banda for banda in bands if banda not in scene.band_names]
    if faltantes:
        raise ValueError(
            f"Las bandas {faltantes} no estan en el Scene "
            f"(band_names={scene.band_names})."
        )

    return np.dstack(
        [
            percentile_stretch(scene.cube[scene.band_names.index(banda)], p_low, p_high)
            for banda in bands
        ]
    )


def _hex_a_rgb(color: str) -> tuple[float, float, float]:
    """Convierte "#rrggbb" a una tupla (r, g, b) en [0,1]."""
    cuerpo = color.lstrip("#")
    return tuple(int(cuerpo[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def scl_to_rgb(scl) -> np.ndarray:
    """Colorea la banda SCL con un color fijo por clase.

    Devuelve la imagen ya en RGB en vez de dejar que `imshow` aplique un
    colormap sobre los codigos. Es la unica forma de garantizar que el color de
    una clase no dependa de que otras clases haya en el recorte: un colormap se
    escala a los valores presentes, asi que un AOI sin nubes y otro con nubes
    dibujarian el suelo desnudo de dos colores distintos mientras la leyenda
    dice que es el mismo.

    Parameters
    ----------
    scl:
        Banda SCL (enteros 0..11), forma (alto, ancho).

    Returns
    -------
    np.ndarray
        Arreglo (alto, ancho, 3) en [0,1], listo para `imshow`. Los codigos que
        no esten en SCL_COLORS se pintan con UNKNOWN_SCL_COLOR.
    """
    codigos = np.asarray(scl)

    rgb = np.empty(codigos.shape + (3,), dtype=float)
    for codigo in np.unique(codigos):
        color = SCL_COLORS.get(int(codigo), UNKNOWN_SCL_COLOR)
        rgb[codigos == codigo] = _hex_a_rgb(color)

    return rgb


def _formato_porcentaje(porcentaje: float) -> str:
    """Formatea un porcentaje con 4 decimales sin aplastar a cero lo presente.

    Una clase que aparece en un solo pixel de 4 millones es 0.000025 %, y con
    "%.4f" se imprime "0.0000 %": la leyenda diria que hay una clase que no
    esta. El umbral se escribe explicito para que se lea como "hay poco", no
    como "no hay".
    """
    if 0.0 < porcentaje < 0.0001:
        return "<0.0001 %"
    return f"{porcentaje:.4f} %"


def _composicion_scl(scl: np.ndarray) -> list[tuple[int, float]]:
    """Clases presentes en el raster con su porcentaje, de mayor a menor.

    Solo las presentes: una leyenda con las 12 clases de SCL_CLASSES sobre un
    AOI que solo tiene 6 sugiere que las otras 6 estan ahi en cantidad
    despreciable, y no estan. El orden por porcentaje decreciente es el mismo
    que imprime `scripts/construir_scene.py`.
    """
    codigos, cuentas = np.unique(scl, return_counts=True)
    total = int(scl.size)

    composicion = [
        (int(codigo), 100.0 * int(cuenta) / total)
        for codigo, cuenta in zip(codigos.tolist(), cuentas.tolist())
    ]
    return sorted(composicion, key=lambda par: par[1], reverse=True)


def plot_scl_classes(scl, mask, axes=None, title: str = ""):
    """Dibuja la clasificacion SCL y la mascara de validez que sale de ella.

    Son dos paneles y no dos figuras porque lo que hay que poder mirar es la
    correspondencia: el SCL es la entrada de la decision y `Scene.mask` es su
    resultado. `preprocessing/masking.py` toma las decisiones menos evidentes
    del preprocesamiento --que clases se descartan, que la mascara sea True
    donde el pixel es valido-- y ninguna produce un error cuando esta al reves.
    Una mascara invertida sobre este desierto despejado deja el AOI entero en
    negro, y eso se ve en un segundo al lado del SCL.

    Parameters
    ----------
    scl:
        Banda SCL (enteros), forma (alto, ancho). Tiene que estar leida sobre
        la misma ventana que `mask` y con remuestreo `nearest`
        (`resampling_for(..., categorical=True)`): interpolar etiquetas inventa
        clases que el producto no trae.
    mask:
        Mascara booleana de la misma forma, True = pixel valido (la convencion
        de `Scene.mask`).
    axes:
        Par de ejes de matplotlib donde dibujar. Si es None se crea una figura
        nueva de dos paneles.
    title:
        Titulo general de la figura. Se aplica como `suptitle`.

    Returns
    -------
    tuple
        Los dos ejes usados: (SCL, mascara).

    Raises
    ------
    ValueError
        Si `scl` y `mask` no tienen la misma forma. Sin esta comprobacion se
        pueden dibujar lado a lado dos ventanas distintas del tile: la figura
        sale perfecta y la comparacion no significa nada.
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    codigos = np.asarray(scl)
    validez = np.asarray(mask, dtype=bool)

    if codigos.shape != validez.shape:
        raise ValueError(
            f"El SCL {codigos.shape} y la mascara {validez.shape} no tienen la "
            "misma forma; son dos ventanas distintas y compararlas no dice nada."
        )

    if axes is None:
        _fig, axes = plt.subplots(1, 2, figsize=(14, 7))
    ax_scl, ax_mask = axes

    composicion = _composicion_scl(codigos)

    ax_scl.imshow(scl_to_rgb(codigos))
    ax_scl.set_title(
        f"Clasificacion de escena (SCL)\n{len(composicion)} clases presentes"
    )
    ax_scl.legend(
        handles=[
            Patch(
                facecolor=SCL_COLORS.get(codigo, UNKNOWN_SCL_COLOR),
                # El borde es lo que hace visibles las clases 0 (negro) y 9
                # (blanco) contra el fondo de la figura.
                edgecolor="black",
                linewidth=0.5,
                label=f"{codigo}: {SCL_CLASSES.get(codigo, 'desconocido')} "
                f"({_formato_porcentaje(porcentaje)})",
            )
            for codigo, porcentaje in composicion
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=2,
        fontsize=8,
        frameon=False,
    )

    descartados = int((~validez).sum())
    porcentaje_validos = 100.0 * float(validez.mean())

    # vmin/vmax explicitos: sin ellos, `imshow` escala al contenido y una
    # mascara sin un solo pixel invalido -- el caso normal en este AOI -- se
    # dibuja negra, que es exactamente lo contrario de lo que significa.
    ax_mask.imshow(validez, cmap="gray", vmin=0, vmax=1)
    ax_mask.set_title(
        f"Mascara de validez (blanco = valido)\n"
        f"{porcentaje_validos:.4f} % validos, {descartados:,} px descartados"
    )

    # Se quitan los ticks pero se conserva el marco. Con `axis("off")` el panel
    # de la mascara, que aqui es casi todo blanco, se funde con el fondo de la
    # figura y no se ve donde termina el AOI.
    for eje in (ax_scl, ax_mask):
        eje.set_xticks([])
        eje.set_yticks([])

    if title:
        ax_scl.figure.suptitle(title)

    return ax_scl, ax_mask


# Numero de barras del histograma de angulos. Es el panel que responde la
# pregunta de coherencia espectral (¿la distribucion tiene estructura o es
# ruido?), y con pocas barras cualquier distribucion parece una campana lisa.
SCORE_HIST_BINS = 60


def plot_score_map(
    score_map,
    scene,
    title: str = "",
    p_low: int = P_LOW_DEFAULT,
    p_high: int = P_HIGH_DEFAULT,
):
    """Dibuja un mapa de puntaje junto al histograma de sus valores validos.

    Son dos paneles y no dos figuras porque son la misma pregunta mirada de dos
    formas. El mapa dice *donde*; el histograma dice *si hay algo que mirar*:
    una distribucion con cola hacia los angulos bajos es evidencia de que el
    detector separa algo, y una campana simetrica sin cola es ruido con
    aspecto de resultado. El mapa solo no distingue esos dos casos.

    Parameters
    ----------
    score_map:
        Mapa de puntaje 2D `(alto, ancho)` tal como lo devuelve
        `Detector.predict`, con NaN en los pixeles invalidos. En Nivel 1 es el
        angulo espectral en radianes.
    scene:
        Scene que produjo el mapa. Aporta `transform` (para poner los ejes en
        coordenadas del CRS en vez de indices de pixel) y `crs` (para
        rotularlos).
    title:
        Titulo general de la figura. Se aplica como `suptitle`.
    p_low, p_high:
        Percentiles del recorte de la escala de color; por defecto 2 y 98, los
        mismos que usa `percentile_stretch`. No se fija la escala al rango
        completo `[0, pi]` a proposito: los angulos reales de una escena
        ocupan una franja estrecha de ese rango (0,16 a 0,45 rad en este AOI),
        asi que estirar el color sobre `[0, pi]` deja el mapa de un solo tono.

    Returns
    -------
    tuple
        Los dos ejes usados: (mapa, histograma).

    Raises
    ------
    ValueError
        Si `score_map` no es 2D o si su forma no calza con la del cubo de
        `scene`. Sin la comprobacion se dibujaria un mapa con los ejes
        georreferenciados de otra ventana.
    """
    import matplotlib.pyplot as plt

    puntajes = np.asarray(score_map, dtype=float)

    if puntajes.ndim != 2:
        raise ValueError(
            f"plot_score_map espera un mapa 2D (alto, ancho); recibi "
            f"{puntajes.ndim} dimensiones con forma {puntajes.shape}."
        )

    forma_escena = tuple(scene.cube.shape[1:])
    if puntajes.shape != forma_escena:
        raise ValueError(
            f"El mapa de puntaje {puntajes.shape} no calza con la forma "
            f"espacial del Scene {forma_escena}; los ejes quedarian en las "
            f"coordenadas de otra ventana."
        )

    finitos = puntajes[np.isfinite(puntajes)]

    # np.nanpercentile y no np.percentile: el mapa llega con NaN en todo lo
    # enmascarado, y con np.percentile un solo NaN devuelve NaN como limite.
    # `imshow` con vmin/vmax NaN no lanza nada, solo dibuja el panel entero
    # plano.
    if finitos.size == 0:
        vmin, vmax = 0.0, float(np.pi)
    else:
        vmin, vmax = (float(v) for v in np.nanpercentile(puntajes, (p_low, p_high)))
        if vmax <= vmin:
            # Mapa constante (o casi): no hay contraste que estirar y una
            # escala invertida haria fallar a imshow.
            vmin, vmax = float(finitos.min()), float(finitos.max())
        if vmax <= vmin:
            vmin, vmax = 0.0, float(np.pi)

    fig, (ax_mapa, ax_hist) = plt.subplots(1, 2, figsize=(14, 6))

    # Ejes en coordenadas del CRS y no en indices de pixel: un mapa cuyo eje
    # dice "1200" no se puede cruzar con ninguna otra capa ni ubicar en un SIG.
    izq, abajo, der, arriba = array_bounds(*puntajes.shape, scene.transform)

    imagen = ax_mapa.imshow(
        puntajes,
        # viridis_r y no viridis: en el SAM el angulo chico es el parecido, o
        # sea que el extremo "interesante" es el minimo. Con la paleta directa
        # lo detectado saldria claro sobre fondo oscuro, al reves de como se
        # lee un mapa de anomalias.
        cmap="viridis_r",
        vmin=vmin,
        vmax=vmax,
        extent=(izq, der, abajo, arriba),
    )
    ax_mapa.set_title(
        "Angulo espectral vs. la firma de referencia\nmas oscuro = mas parecido"
    )
    ax_mapa.set_xlabel(f"Este ({scene.crs.to_string()})")
    ax_mapa.set_ylabel("Norte")

    barra = fig.colorbar(imagen, ax=ax_mapa, fraction=0.046)
    # La unidad va en la barra y no en el titulo: el numero que se lee ahi es
    # un angulo en radianes, y sin decirlo se confunde con un puntaje en [0,1].
    barra.set_label("Angulo espectral (rad)")

    ax_hist.hist(finitos, bins=SCORE_HIST_BINS, color="#3b528b")
    ax_hist.axvline(vmin, color="black", linestyle="--", linewidth=1)
    ax_hist.axvline(
        vmax,
        color="black",
        linestyle="--",
        linewidth=1,
        label=f"escala de color (p{p_low}-p{p_high})",
    )
    ax_hist.set_title(
        f"Distribucion de los angulos validos\n{finitos.size:,} px validos"
    )
    ax_hist.set_xlabel("Angulo espectral (rad)")
    ax_hist.set_ylabel("Pixeles")
    ax_hist.legend(fontsize=8, frameon=False)

    if title:
        fig.suptitle(title)
    fig.tight_layout()

    return ax_mapa, ax_hist
