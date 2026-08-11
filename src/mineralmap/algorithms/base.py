"""Clase abstracta Detector: interfaz comun para todos los algoritmos de deteccion."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Detector(ABC):
    """Contrato comun a todos los detectores (SAM, Random Forest, unmixing, ...).

    El pipeline no conoce el algoritmo concreto. Le pregunta tres cosas y no
    asume ninguna: que bandas consume (`bands`), en que direccion apunta su
    puntaje (`higher_is_better`, a traves de `detects`) y cuanto vale cada
    pixel (`predict`).
    """

    # Direccion del puntaje, declarada por cada detector. El pipeline la
    # consulta en vez de asumir la de SAM. Ver decisiones tecnicas seccion 8.
    higher_is_better: bool = True

    # Bandas que consume el detector, en nombres canonicos y en el orden con
    # que las quiere. None significa "todas las del Scene". El pipeline
    # subconjunta con esto y pide la firma de referencia con el mismo orden.
    bands: tuple[str, ...] | None = None

    @abstractmethod
    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Calcula el mapa de puntaje de deteccion del mineral en la escena.

        Parameters
        ----------
        cube:
            Cubo de reflectancia de la escena, forma (n_bandas, alto, ancho).
            El llamador ya lo subconjunto a las bandas que declara `bands`.
        reference:
            Firma espectral de referencia del mineral objetivo, forma
            (n_bandas,), alineada posicionalmente con el eje 0 de `cube`.

        Returns
        -------
        np.ndarray
            Mapa de puntaje 2D, forma (alto, ancho). **La direccion la declara
            cada detector en `higher_is_better`**, y quien quiera binarizar el
            mapa usa `detects()` en vez de comparar a mano.

            Este contrato decia "a mayor valor, mayor evidencia" como si fuera
            universal, y el unico detector implementado va al reves: `SAM`
            devuelve un angulo espectral, donde MENOR es mas parecido. No es un
            descuido de SAM. El documento 05 del proyecto define el puntaje del
            SAM como el angulo mismo ("angulo pequeno = alta similitud"), y todo
            lo que consume el detector asume esa direccion: el `viridis_r` de
            los mapas, el `angle_threshold_rad` de los configs y `threshold()`,
            que detecta con `<=`.

            Se resolvio declarando la direccion en vez de normalizar los
            detectores a "mayor es mejor" (para SAM habria sido devolver el
            coseno). Normalizar habria invertido el signo de SAM para que
            calzara con un contrato interno, perdiendo la unidad fisica del
            angulo --que es la del SAM en la literatura-- y obligando a tocar la
            paleta, el umbral del config y `threshold()`. Ver
            `docs/es/decisiones_tecnicas.md`, seccion 8.
        """
        ...

    def detects(self, scores: np.ndarray, threshold_value: float) -> np.ndarray:
        """Mascara booleana de deteccion segun la direccion declarada.

        Un detector que no declare `higher_is_better` hereda el sentido del
        contrato. Sin este metodo el pipeline aplicaba el `<=` de SAM a la
        salida de cualquier detector, y un puntaje donde mayor es mejor daba
        cero detecciones sin lanzar nada: un detector que devolviera 0,9 en
        todos los pixeles --evidencia maxima-- se reportaba como cero
        detecciones bajo todos los umbrales del barrido.

        Parameters
        ----------
        scores:
            Mapa de puntaje 2D tal como lo devuelve `predict`. Puede traer NaN.
        threshold_value:
            Umbral con el que binarizar, en las unidades del puntaje.

        Returns
        -------
        np.ndarray
            Mascara booleana de la misma forma. Los pixeles NaN salen False por
            la semantica de IEEE-754 (toda comparacion contra NaN es falsa), que
            es lo que corresponde: un pixel sin dato no es una deteccion.
        """
        if self.higher_is_better:
            return scores >= threshold_value
        return scores <= threshold_value
