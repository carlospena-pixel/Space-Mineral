"""Clasificador Random Forest (Nivel 2)."""

from __future__ import annotations

import numpy as np

from mineralmap.algorithms.base import Detector


class RandomForestDetector(Detector):
    """Detector supervisado por Random Forest. Andamiaje de Nivel 2.

    No esta implementado y no esta en `pipeline.DETECTORS`: el pipeline no lo
    puede instanciar todavia. Lo que si esta es la firma, alineada al contrato.

    Por que la firma importa aunque el cuerpo lance NotImplementedError
    ------------------------------------------------------------------
    Esta clase declaraba `predict(self, cube)` --- un argumento menos que
    `Detector.predict(self, cube, reference)`. Python no comprueba las firmas al
    heredar, asi que la contradiccion no rompia nada mientras el cuerpo lanzara
    `NotImplementedError`: el error llegaba antes que cualquier problema de
    argumentos. El dia que alguien escribiera el cuerpo, el pipeline lo llamaria
    con dos argumentos y reventaria con un `TypeError` a mitad de una corrida
    larga, lejos de la causa. Se alinea ahora, que cuesta una linea, en vez de
    entonces.

    `higher_is_better` se hereda del contrato como `True`, que es lo correcto
    para este detector: su puntaje sera la probabilidad de la clase objetivo, y
    ahi mayor es mas evidencia. No se redeclara porque repetir un valor que ya
    coincide con el default crea un segundo sitio que actualizar.
    """

    def fit(self, cube: np.ndarray, reference: np.ndarray) -> RandomForestDetector:
        """Entrena el bosque con las muestras etiquetadas de la escena.

        **Esto no es parte del contrato `Detector`.** Es una extension propia de
        los detectores entrenables, y se deja declarada a proposito para que el
        hueco quede visible: `Detector` supone que un detector es una funcion
        del par (cubo, referencia), y un clasificador supervisado no lo es
        --- necesita un paso previo con estado ---. Resolver eso es parte del
        trabajo de Nivel 2, no algo que se pueda decidir aqui de pasada.

        Raises
        ------
        NotImplementedError
            Siempre. Nivel 2.
        """
        raise NotImplementedError

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Mapa de probabilidad de la clase objetivo, forma `(alto, ancho)`.

        Firma del contrato; ver `Detector.predict`.

        Raises
        ------
        NotImplementedError
            Siempre. Nivel 2.
        """
        raise NotImplementedError
