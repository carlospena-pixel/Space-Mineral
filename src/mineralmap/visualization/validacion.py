"""Figuras de la etapa de validacion: curva ROC y distribucion por clase.

Son las dos figuras que responden preguntas distintas sobre el mismo par de
rasters. La ROC dice **cuanto separa** el detector, integrando sobre todos los
umbrales posibles; el histograma por clase dice **por que** separa o no,
mostrando las dos distribuciones que la ROC resume en un solo numero.

Las dos van juntas a proposito: un AUC solo no distingue "las distribuciones se
superponen" de "estan separadas pero al reves", y esas dos lecturas llevan a
decisiones opuestas.
"""

from __future__ import annotations

import numpy as np

from mineralmap.visualization.maps import GROUND_TRUTH_COLORS, GROUND_TRUTH_LABELS

# Numero de barras del histograma por clase. Alto por el mismo motivo que
# SCORE_HIST_BINS en maps.py: la pregunta es si las dos distribuciones tienen
# estructura y donde se cruzan, y con pocas barras cualquier par de
# distribuciones parece dos campanas limpias que no se tocan.
HIST_BINS = 80

# Color de la diagonal de azar en la ROC. Gris y punteada para que no compita
# con la curva: es la referencia, no un resultado.
COLOR_AZAR = "#999999"

# Numero maximo de puntos que se dibujan de la curva. Con 238.203 puntos
# matplotlib tarda y el PNG pesa, y a la resolucion de la figura los puntos
# intermedios caen sobre el mismo pixel. El submuestreo es **solo del dibujo**:
# el AUC y los umbrales optimos se calculan siempre sobre la curva completa,
# porque un codo perdido en el submuestreo desplazaria el umbral reportado.
MAX_PUNTOS_DIBUJADOS = 4000


def _submuestrear(fpr: np.ndarray, tpr: np.ndarray):
    """Reduce la curva a MAX_PUNTOS_DIBUJADOS conservando los extremos.

    Se toma un paso constante en indice y se fuerzan el primer y el ultimo
    punto: sin ellos la curva dibujada no arrancaria en (0,0) ni terminaria en
    (1,1) y pareceria truncada.
    """
    n = fpr.size
    if n <= MAX_PUNTOS_DIBUJADOS:
        return fpr, tpr

    indices = np.unique(
        np.r_[
            np.linspace(0, n - 1, MAX_PUNTOS_DIBUJADOS).astype(int),
            [0, n - 1],
        ]
    )
    return fpr[indices], tpr[indices]


def plot_curva_roc(curva, title: str = "", ax=None):
    """Dibuja la curva ROC con la diagonal de azar y los dos umbrales optimos.

    Parameters
    ----------
    curva:
        `CurvaROC` tal como la devuelve
        `mineralmap.validation.metrics.curva_roc`. Se le piden `fpr`, `tpr`,
        `auc`, `umbral_youden`, `youden_j`, `umbral_f1` y `f1_maximo`. Se recibe
        el objeto entero en vez de los arreglos sueltos para que la figura no
        pueda rotular un AUC calculado sobre otros datos que la curva dibujada.
    title:
        Titulo de la figura.
    ax:
        Eje donde dibujar. `None` crea una figura nueva.

    Returns
    -------
    matplotlib.axes.Axes
        El eje usado.

    Raises
    ------
    ValueError
        Si `fpr` y `tpr` no tienen el mismo largo, o si la curva esta vacia.
    """
    import matplotlib.pyplot as plt

    fpr = np.asarray(curva.fpr, dtype=float)
    tpr = np.asarray(curva.tpr, dtype=float)

    if fpr.shape != tpr.shape:
        raise ValueError(
            f"fpr {fpr.shape} y tpr {tpr.shape} no tienen el mismo largo; la "
            "curva no se puede dibujar."
        )
    if fpr.size == 0:
        raise ValueError("La curva ROC esta vacia; no hay nada que dibujar.")

    if ax is None:
        _, ax = plt.subplots(figsize=(6.5, 6.5))

    fpr_dibujo, tpr_dibujo = _submuestrear(fpr, tpr)

    ax.plot([0, 1], [0, 1], linestyle="--", color=COLOR_AZAR, linewidth=1)
    # La diagonal se rotula con su valor y no solo como "azar": un AUC por
    # debajo de 0,5 se lee de un vistazo como "la curva va por debajo de esta
    # linea", que es la lectura correcta y la que se pierde si la referencia no
    # tiene numero.
    ax.text(
        0.62,
        0.56,
        "azar (AUC = 0,50)",
        color=COLOR_AZAR,
        rotation=45,
        rotation_mode="anchor",
        fontsize=9,
    )

    ax.plot(fpr_dibujo, tpr_dibujo, color="#3b528b", linewidth=1.8)
    ax.fill_between(fpr_dibujo, tpr_dibujo, alpha=0.12, color="#3b528b")

    # El AUC y los dos umbrales operativos van rotulados dentro de los ejes y no
    # en el titulo: la figura se pega en presentaciones recortada al area de
    # dibujo, y el numero que da sentido a la curva no puede quedar fuera del
    # recorte.
    ax.annotate(
        f"AUC = {curva.auc:.4f}",
        xy=(0.55, 0.10),
        fontsize=13,
        fontweight="bold",
        color="#3b528b",
    )
    ax.annotate(
        f"Youden: umbral {curva.umbral_youden:.4f} rad   J = {curva.youden_j:.4f}\n"
        f"F1 max: umbral {curva.umbral_f1:.4f} rad   F1 = {curva.f1_maximo:.4f}",
        xy=(0.55, 0.02),
        fontsize=9,
        color="#333333",
    )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.set_xlabel("Tasa de falsos positivos (FPR)")
    ax.set_ylabel("Tasa de verdaderos positivos (TPR)")
    ax.set_title(title or "Curva ROC")

    return ax


def plot_histograma_por_clase(
    y_true, y_score, umbral: float | None = None, title: str = "", ax=None
):
    """Superpone las distribuciones del puntaje de las dos clases evaluables.

    Es el panel que explica el AUC. Si las dos distribuciones se pisan, el AUC
    ronda 0,5 porque no hay nada que separar; si estan separadas pero con la
    clase positiva del lado del puntaje **mayor**, el AUC cae por debajo de 0,5
    y el detector esta ordenando al reves de como declara. Las dos situaciones
    dan un AUC bajo y solo esta figura las distingue.

    Parameters
    ----------
    y_true:
        Etiquetas en {0, 1}, ya filtradas por
        `mineralmap.validation.metrics.preparar_pares`.
    y_score:
        Puntaje continuo alineado, en las unidades del detector.
    umbral:
        Umbral a marcar con una linea vertical. `None` no dibuja ninguna.
    title:
        Titulo de la figura.
    ax:
        Eje donde dibujar. `None` crea una figura nueva.

    Returns
    -------
    matplotlib.axes.Axes
        El eje usado.

    Raises
    ------
    ValueError
        Si los dos arreglos no tienen el mismo largo, o si falta alguna de las
        dos clases: un histograma "por clase" con una sola clase presente
        dibuja una distribucion y rotula dos, que es peor que no dibujar nada.
    """
    import matplotlib.pyplot as plt

    verdad = np.asarray(y_true).ravel()
    puntaje = np.asarray(y_score, dtype=float).ravel()

    if verdad.shape != puntaje.shape:
        raise ValueError(
            f"y_true {verdad.shape} y y_score {puntaje.shape} no tienen el "
            "mismo largo."
        )

    positivos = puntaje[verdad == 1]
    negativos = puntaje[verdad == 0]
    if positivos.size == 0 or negativos.size == 0:
        raise ValueError(
            f"Falta una de las dos clases (positivos: {positivos.size}, "
            f"negativos: {negativos.size}); el histograma por clase rotularia "
            "dos distribuciones y dibujaria una."
        )

    if ax is None:
        _, ax = plt.subplots(figsize=(9, 5))

    # Los mismos bordes para las dos clases: con bins independientes las barras
    # quedan desplazadas entre si y el solapamiento aparente no es el real.
    bordes = np.linspace(puntaje.min(), puntaje.max(), HIST_BINS + 1)

    # `density=True` y no conteos: hay 3,8 veces mas negativos que positivos, y
    # en conteos crudos la clase positiva es una linea plana al pie de la otra.
    # La pregunta de esta figura es donde cae cada distribucion, no cuantos
    # pixeles tiene cada una --- eso lo dice la tabla de metricas ---.
    for valor, datos in ((0, negativos), (1, positivos)):
        ax.hist(
            datos,
            bins=bordes,
            density=True,
            alpha=0.55,
            color=GROUND_TRUTH_COLORS[valor],
            label=f"{GROUND_TRUTH_LABELS[valor]}  (n = {datos.size:,})",
        )

    for valor, datos in ((0, negativos), (1, positivos)):
        ax.axvline(
            float(np.median(datos)),
            color=GROUND_TRUTH_COLORS[valor],
            linestyle="-",
            linewidth=1.6,
        )

    if umbral is not None:
        ax.axvline(
            float(umbral),
            color="black",
            linestyle="--",
            linewidth=1.4,
            label=f"umbral del config ({umbral:.4f} rad)",
        )

    ax.set_xlabel("Angulo espectral (rad)   ---   menor = mas parecido a la firma")
    ax.set_ylabel("Densidad de pixeles")
    ax.set_title(
        title
        or "Distribucion del angulo por clase de verdad de terreno\n"
        "las lineas verticales de color son las medianas"
    )
    ax.legend(fontsize=8, frameon=False)

    return ax
