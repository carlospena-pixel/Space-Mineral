"""Spectral Angle Mapper (SAM): deteccion por angulo espectral entre cada pixel
y una firma de referencia.
"""

from __future__ import annotations

import numpy as np

from mineralmap.algorithms.base import Detector


class SAM(Detector):
    """Detector basado en el angulo espectral (Spectral Angle Mapper).

    Mide la similitud entre cada pixel del cubo y una firma de referencia
    como el angulo entre ambos vectores en el espacio de bandas. Al depender
    solo de la direccion del vector (no de su magnitud), es invariante a
    variaciones de iluminacion/albedo.

    El puntaje que devuelve es el angulo, o sea que **menor es mas parecido**.
    Es la direccion contraria a la que declara el docstring de `Detector`; la
    tension esta anotada ahi y en `docs/es/decisiones_tecnicas.md`.
    """

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Calcula el mapa de angulo espectral entre `cube` y `reference`.

        La banda `i` del cubo tiene que ser la componente `i` de la firma: el
        producto punto asume esa alineacion posicional y no tiene ninguna forma
        de verificarla desde adentro. Quien arma los dos vectores es el llamador,
        subconjuntando el cubo y pidiendo la firma con el mismo `band_order`
        (ver `decisiones_tecnicas.md` seccion 1.1).

        Que pasa con los pixeles que no son un dato:

        - **Pixel con NaN en alguna banda** -> NaN en ese pixel, y solo en ese.
          Es entrada legitima y soportada: el pipeline entrega el cubo ya
          enmascarado con `preprocessing.masking.apply_mask`, que pone NaN en
          todas las bandas de los pixeles invalidos. Enmascarar es trabajo del
          consumidor, no de este metodo, y por eso `predict` no recibe mascara.
        - **Pixel de norma cero** (todas las bandas exactamente en 0) -> NaN.
          Un vector nulo no tiene direccion, asi que el angulo contra el no es
          cero ni pi/2: no esta definido. Devolver 0 lo declararia coincidencia
          perfecta y lo pintaria como la deteccion mas fuerte del mapa, que es
          el peor error posible aca. NaN lo deja fuera del mapa por el mismo
          camino que un pixel enmascarado, y `threshold` ya lo descarta.

        Parameters
        ----------
        cube:
            Cubo de reflectancia de la escena, forma (n_bandas, alto, ancho).
            Puede traer NaN. Un cubo de dtype entero se promueve a float32,
            igual que en `apply_mask`.
        reference:
            Firma espectral de referencia del mineral objetivo, forma
            (n_bandas,), alineada posicionalmente con el eje 0 de `cube`.

        Returns
        -------
        np.ndarray
            Mapa de angulo espectral en radianes, forma (alto, ancho), en el
            rango [0, pi] y en float64. Menor angulo = mayor parecido. Los
            pixeles invalidos (NaN en `cube`, o norma cero) devuelven NaN.

        Raises
        ------
        ValueError
            Si `cube` no es 3D, si `reference` no es 1D, si el numero de bandas
            de ambos no coincide, si `reference` trae algun valor no finito, o
            si `reference` tiene norma cero.
        """
        cube = np.asarray(cube)
        reference = np.asarray(reference, dtype=np.float64)

        if cube.ndim != 3:
            raise ValueError(
                f"El cubo debe tener forma (n_bandas, alto, ancho); recibi "
                f"{cube.ndim} dimensiones con forma {cube.shape}."
            )

        # Una firma de forma (n, 1) no rompe nada: hace broadcast y devuelve un
        # mapa de la forma equivocada, con numeros que se ven razonables.
        if reference.ndim != 1:
            raise ValueError(
                f"La firma de referencia debe ser un vector 1D de forma "
                f"(n_bandas,); recibi {reference.ndim} dimensiones con forma "
                f"{reference.shape}."
            )

        if cube.shape[0] != reference.shape[0]:
            raise ValueError(
                f"El cubo trae {cube.shape[0]} bandas y la firma de referencia "
                f"{reference.shape[0]}: tienen que ser la misma cantidad y estar "
                f"alineadas posicionalmente. El cruce tipico es un cubo de "
                f"BAND_ORDER (12 bandas) contra una firma de SAM_BANDS (9), o al "
                f"reves; subconjunta el cubo y pide la firma con el mismo "
                f"band_order."
            )

        # Un NaN en la firma no es un caso legitimo, a diferencia de uno en el
        # cubo: `get_reference_spectrum` lee las 12 posiciones del archivo USGS
        # y no puede producirlo salvo que el archivo este roto. Y contamina de
        # una forma particularmente dificil de diagnosticar: entra en la norma,
        # el coseno sale NaN en TODOS los pixeles, y el mapa resultante es
        # indistinguible de una escena enteramente enmascarada. Falla ruidosa.
        if not np.isfinite(reference).all():
            raise ValueError(
                f"La firma de referencia tiene valores no finitos (NaN o inf) en "
                f"las posiciones {np.flatnonzero(~np.isfinite(reference)).tolist()}. "
                f"Una firma con NaN vuelve NaN el mapa entero y el resultado es "
                f"indistinguible de una escena completamente enmascarada."
            )

        norma_referencia = float(np.linalg.norm(reference))
        if norma_referencia == 0.0:
            raise ValueError(
                f"La firma de referencia tiene norma {norma_referencia}: no tiene "
                f"ninguna direccion contra la cual medir un angulo. Es el mismo "
                f"criterio que aplica `visualization.spectra.normalize_signature`."
            )

        # Un cubo entero no puede alimentar un einsum con acumulador float64 sin
        # un casteo inseguro; se promueve a float32, el dtype con que viaja la
        # reflectancia en todo el proyecto, igual que hace `apply_mask`.
        if not np.issubdtype(cube.dtype, np.floating):
            cube = cube.astype(np.float32)

        # `dtype=np.float64` fija el acumulador de la suma, NO castea el cubo:
        # las bandas siguen entrando en float32 y el cubo real (12, 2000, 2000)
        # sigue ocupando 183 MB en vez de los 366 MB que costaria un
        # `cube.astype(np.float64)`. Lo unico que se materializa en float64 son
        # los dos mapas (alto, ancho), 30,5 MB cada uno en esa escena.
        #
        # Por que no alcanza con acumular en float32. Medido sobre un cubo de
        # 9 bandas contra el mismo calculo en float64 puro:
        #   - pixeles arbitrarios:  error maximo 3,8e-7 rad
        #   - pixeles casi identicos a la firma: error maximo 4,5e-4 rad
        # El segundo caso es el que importa, porque es exactamente el de una
        # deteccion. Cerca de coseno = 1 la derivada de arccos diverge y
        # amplifica el redondeo: ahi el angulo verdadero medido era 1,3e-5 rad,
        # o sea que el error era 35 veces mas grande que la cantidad que se
        # estaba midiendo. Con el acumulador en float64 ese error baja a
        # 3,9e-8 rad, identico al que da castear el cubo entero, y es lo que
        # permite que los casos analiticos de los tests cierren a 1e-12.
        producto_punto = np.einsum("bhw,b->hw", cube, reference, dtype=np.float64)
        norma_pixel = np.sqrt(np.einsum("bhw,bhw->hw", cube, cube, dtype=np.float64))

        with np.errstate(invalid="ignore", divide="ignore"):
            coseno = producto_punto / (norma_pixel * norma_referencia)
        coseno = np.clip(coseno, -1.0, 1.0)

        return np.arccos(coseno)


def threshold(angle_map: np.ndarray, max_angle: float) -> np.ndarray:
    """Genera una mascara booleana de deteccion a partir del mapa de angulos.

    Parameters
    ----------
    angle_map:
        Mapa de angulo espectral en radianes, forma (alto, ancho). Puede traer
        NaN en los pixeles invalidos, que es lo que devuelve `SAM.predict`.
    max_angle:
        Angulo maximo (en radianes) por debajo del cual se considera deteccion.

    Returns
    -------
    np.ndarray
        Mascara booleana, forma (alto, ancho): True donde angle_map <= max_angle.
        Los pixeles NaN salen False, que es lo que corresponde (un pixel sin
        dato no es una deteccion). Esto no se programa: es la semantica de
        IEEE-754, donde toda comparacion contra NaN es falsa. Queda escrito
        porque el comportamiento correcto sale gratis y por accidente, y una
        reimplementacion que "arreglara" los NaN antes de comparar (por ejemplo
        con `np.nan_to_num`) los convertiria en 0.0 y por lo tanto en
        detecciones, que es el error opuesto y silencioso.
    """
    return angle_map <= max_angle
