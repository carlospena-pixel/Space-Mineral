"""Clase abstracta Detector: interfaz comun para todos los algoritmos de deteccion."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Detector(ABC):
    """Contrato comun a todos los detectores (SAM, Random Forest, unmixing, ...).

    El pipeline no conoce el algoritmo concreto: solo llama a predict() con
    el cubo de la escena y la firma de referencia del mineral objetivo.
    """

    @abstractmethod
    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Calcula el mapa de puntaje de deteccion del mineral en la escena.

        Parameters
        ----------
        cube:
            Cubo de reflectancia de la escena, forma (n_bandas, alto, ancho).
        reference:
            Firma espectral de referencia del mineral objetivo, forma (n_bandas,).

        Returns
        -------
        np.ndarray
            Mapa de puntaje 2D, forma (alto, ancho): a mayor valor, mayor
            probabilidad/similitud de presencia del mineral segun el algoritmo.

            DEUDA ABIERTA, no resolver sin acordarlo. El unico detector
            implementado hoy va en la direccion contraria: `SAM.predict`
            devuelve un angulo espectral, donde MENOR es mas parecido. No es un
            descuido de SAM. El documento 05 del proyecto define el puntaje del
            SAM como el angulo mismo ("angulo pequeno = alta similitud"), y todo
            lo que ya consume el detector asume esa direccion: el `viridis_r` de
            los mapas, el `angle_threshold_rad` de los configs y `threshold()`,
            que detecta con `<=`. El que quedo redactado para un puntaje que
            ningun detector produce todavia es este contrato.

            Invertir el signo de SAM para que calce con este texto romperia la
            visualizacion y los umbrales sin lanzar ningun error: los mapas
            seguirian dibujandose, con la escala de color al reves. Las dos
            salidas posibles son reescribir este parrafo para admitir puntajes
            con direccion declarada por cada detector, o normalizar los
            detectores a "mayor es mejor" (para SAM seria devolver el coseno, no
            el angulo). Hay que decidirlo ANTES de que entre el segundo
            detector, porque a partir de ahi el pipeline tiene que comparar
            puntajes de algoritmos distintos y necesita saber que significan.
            Ver `docs/es/decisiones_tecnicas.md`, seccion 8.
        """
        ...
