"""Indices espectrales derivados de la reflectancia: por ahora, el clay ratio.

Por que vive en `spectral/` y no en `validation/`. Un indice espectral es una
combinacion de bandas de reflectancia, del mismo tipo de objeto que la firma de
referencia: se calcula desde el cubo y describe la superficie. `validation/`
compara mascaras ya construidas y no sabe que es una banda. Meter el clay ratio
en `validation/metrics.py` obligaria a ese modulo a conocer nombres de banda y
romperia su contrato de "entra numpy, sale numpy" (ver
`docs/es/decisiones_tecnicas.md`, seccion 1).
"""

from __future__ import annotations

import numpy as np

# Las dos bandas del clay ratio, en nombres canonicos sin cero (el estilo de
# `config.BAND_ORDER`). No se importan de `config` a proposito: no son una
# configuracion del proyecto sino la definicion misma del indice, y si algun dia
# `SAM_BANDS` dejara de incluirlas el indice seguiria siendo B11/B12.
BANDA_HOMBRO = "B11"  # ~1610 nm en S2B: fuera del rasgo de absorcion
BANDA_ABSORCION = "B12"  # ~2186 nm en S2B: sobre el doblete Al-OH


def clay_ratio(cube: np.ndarray, band_names: list[str]) -> np.ndarray:
    """Calcula el clay ratio B11/B12 de cada pixel del cubo.

    **Direccion del indice, y por que hay que escribirla.** La caolinita tiene
    un doblete de absorcion Al-OH en 2160 y 2200 nm, que cae dentro de B12
    (~2186 nm en S2B). B11 (~1610 nm) queda fuera del rasgo y funciona como
    hombro de referencia. Donde hay arcilla, entonces, B12 baja y B11 no: el
    cociente B11/B12 **sube donde hay arcilla**.

    Es la **direccion contraria a la del angulo SAM**, donde MENOR es mas
    parecido. Al cruzar los dos mapas hay que umbralizar cada uno en su propio
    sentido: la mascara de SAM se saca con `angulo <= umbral` y la del clay
    ratio con `ratio >= umbral`. Umbralizar los dos en el mismo sentido no lanza
    ningun error y produce dos mascaras que son casi complementarias, con lo cual
    el IoU entre ellas sale cercano a cero y se lee como "los dos criterios no
    coinciden" cuando en realidad uno se calculo al reves.

    El indice **no** es una deteccion de caolinita. B11/B12 sube con cualquier
    material que absorba en el infrarrojo de onda corta --otras arcillas,
    micas, carbonatos, y tambien vegetacion seca-- y es sensible al albedo de
    una forma que el angulo espectral no lo es. Sirve como segunda opinion
    independiente del SAM, no como verdad de terreno.

    Parameters
    ----------
    cube:
        Cubo de reflectancia, forma (n_bandas, alto, ancho). Puede traer NaN en
        los pixeles enmascarados, que se propagan al resultado.
    band_names:
        Nombre de cada banda del cubo, alineado posicionalmente con el eje 0.
        Las bandas se localizan **por nombre** y no por indice fijo: el cubo
        llega a veces con las 12 bandas de `BAND_ORDER` y a veces con las 9 de
        `SAM_BANDS`, y B11 esta en la posicion 10 en el primero y en la 7 en el
        segundo. Un indice fijo apuntaria a otra banda segun cual sea el cubo y
        devolveria un mapa de aspecto perfectamente razonable calculado sobre
        las bandas equivocadas.

    Returns
    -------
    np.ndarray
        Mapa 2D del cociente B11/B12, forma (alto, ancho), en float64. Los
        pixeles con B12 igual a 0 devuelven NaN, no inf: un cociente infinito se
        colaria como el valor mas alto del mapa y por lo tanto como la deteccion
        de arcilla mas fuerte, que es el mismo modo de falla que
        `algorithms.sam.predict` evita al devolver NaN en los pixeles de norma
        cero. Los NaN del cubo se propagan.

    Raises
    ------
    ValueError
        Si `cube` no es 3D, si `band_names` no tiene un nombre por banda del
        cubo, o si falta B11 o B12 (el mensaje nombra cual falta y que bandas
        si llegaron).
    """
    cube = np.asarray(cube)

    if cube.ndim != 3:
        raise ValueError(
            f"El cubo debe tener forma (n_bandas, alto, ancho); recibi "
            f"{cube.ndim} dimensiones con forma {cube.shape}."
        )

    if len(band_names) != cube.shape[0]:
        raise ValueError(
            f"`band_names` trae {len(band_names)} nombres y el cubo "
            f"{cube.shape[0]} bandas; tiene que haber uno por banda para que la "
            f"busqueda por nombre signifique algo."
        )

    faltantes = [
        banda for banda in (BANDA_HOMBRO, BANDA_ABSORCION) if banda not in band_names
    ]
    if faltantes:
        raise ValueError(
            f"El clay ratio necesita {BANDA_HOMBRO} y {BANDA_ABSORCION}, y "
            f"falta{'n' if len(faltantes) > 1 else ''} {faltantes} en el cubo. "
            f"Las bandas recibidas son {list(band_names)}."
        )

    hombro = cube[band_names.index(BANDA_HOMBRO)].astype(np.float64)
    absorcion = cube[band_names.index(BANDA_ABSORCION)].astype(np.float64)

    # Mismo patron que `sam.predict`: la division se hace sin avisos y el caso
    # degenerado se corrige despues, en vez de recorrer el mapa con una mascara
    # previa. numpy convierte x/0 en +-inf (o NaN si x tambien es 0), y son los
    # inf los que hay que sacar: un inf es el maximo del mapa y sobreviviria a
    # cualquier umbral por percentil.
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = hombro / absorcion

    return np.where(np.isfinite(ratio), ratio, np.nan)


def mask_by_positive_rate(
    index_map: np.ndarray,
    positive_rate: float,
    valid: np.ndarray | None = None,
    higher_is_better: bool = True,
) -> np.ndarray:
    """Marca la fraccion `positive_rate` de pixeles con mejor puntaje del mapa.

    **Por que por percentil y no por un umbral absoluto.** El clay ratio no
    tiene un valor de corte canonico: no existe un "B11/B12 > 1,35" publicado
    que signifique arcilla, porque el cociente depende de la correccion
    atmosferica, del albedo local y del rango espectral del sensor. Inventar un
    numero absoluto seria elegir la tasa de positivos sin decirlo.

    **Y por que la tasa tiene que ser la misma que la de la mascara con la que
    se va a comparar.** El IoU entre dos mascaras de tamanos muy distintos esta
    acotado por el cociente de sus tamanos: si una marca 62 pixeles y la otra
    400.000, el IoU no puede pasar de 62/400.000 aunque los 62 esten todos
    dentro de los 400.000. En ese caso el numero mide la diferencia de tamano y
    no el acuerdo espacial, y se leeria como desacuerdo. Igualar la tasa de
    positivos es lo que hace que el IoU vuelva a hablar de donde caen los
    pixeles.

    Parameters
    ----------
    index_map:
        Mapa 2D del indice, forma (alto, ancho). Sus NaN nunca se marcan.
    positive_rate:
        Fraccion de los pixeles validos a marcar, en (0, 1]. Con 0,002 % se
        escribe `2e-5`.
    valid:
        Mascara booleana opcional de pixeles evaluables, misma forma. Los
        pixeles invalidos no se marcan y tampoco cuentan para el total sobre el
        que se calcula la fraccion.
    higher_is_better:
        True (default) marca los valores mas **altos**, que es lo que
        corresponde al clay ratio. False marca los mas bajos, que es lo que
        corresponderia a un mapa de angulo espectral. Es el mismo parametro
        explicito que `validation.metrics.roc_curve`, y por el mismo motivo:
        mirando un arreglo de flotantes no hay forma de saber en que direccion
        va su escala.

    Returns
    -------
    np.ndarray
        Mascara booleana de la forma de `index_map`. Marca exactamente
        ``round(positive_rate * n_validos)`` pixeles, salvo que ese redondeo de
        0 (entonces no marca ninguno) o que haya menos validos que eso.

    Raises
    ------
    ValueError
        Si `index_map` no es 2D, si `positive_rate` no esta en (0, 1], o si
        `valid` no calza con la forma del mapa.
    """
    index_map = np.asarray(index_map, dtype=np.float64)

    if index_map.ndim != 2:
        raise ValueError(
            f"`index_map` debe ser un mapa 2D (alto, ancho); recibi "
            f"{index_map.ndim} dimensiones con forma {index_map.shape}."
        )

    if not 0.0 < positive_rate <= 1.0:
        raise ValueError(
            f"`positive_rate` es una fraccion en (0, 1]; recibi {positive_rate}. "
            f"Para el 0,002 % se escribe 2e-5, no 0.002."
        )

    evaluables = np.isfinite(index_map)
    if valid is not None:
        valid = np.asarray(valid)
        if valid.shape != index_map.shape:
            raise ValueError(
                f"La mascara `valid` tiene forma {valid.shape} y el mapa "
                f"{index_map.shape}: una mascara de otra ventana marcaria "
                f"pixeles arbitrarios sin que nada lo denuncie."
            )
        evaluables &= valid.astype(bool)

    indices_validos = np.flatnonzero(evaluables.ravel())
    cuantos = min(
        int(round(positive_rate * indices_validos.size)), indices_validos.size
    )

    # Se arma plana y se reconstruye al final: `mascara.ravel()[idx] = True`
    # solo funciona mientras `ravel()` devuelva una vista, que depende de la
    # contiguidad del arreglo y no del contrato de numpy.
    plana = np.zeros(index_map.size, dtype=bool)
    if cuantos == 0:
        return plana.reshape(index_map.shape)

    valores = index_map.ravel()[indices_validos]
    orientados = valores if higher_is_better else -valores

    # `argpartition` en vez de ordenar el mapa entero: sobre 4 millones de
    # pixeles es O(n) contra O(n log n), y aca solo interesa cuales son los k
    # mejores, no en que orden quedan entre ellos.
    #
    # Se toman exactamente k pixeles en vez de cortar por el valor del percentil.
    # Con un percentil, un grupo de empates justo en el corte entra entero o no
    # entra, y la tasa de positivos realizada deja de ser la pedida --que es
    # justamente la propiedad por la que existe esta funcion--. Los empates se
    # rompen por orden de pixel, que es arbitrario pero determinista; con
    # reflectancia continua no se dan en la practica.
    mejores = np.argpartition(-orientados, cuantos - 1)[:cuantos]
    plana[indices_validos[mejores]] = True
    return plana.reshape(index_map.shape)
