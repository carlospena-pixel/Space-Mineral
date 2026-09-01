"""Spectral unmixing (Nivel 3)."""

from __future__ import annotations

import numpy as np

from mineralmap.algorithms.base import Detector


class UnmixingDetector(Detector):
    """Desmezcla espectral lineal. Andamiaje de Nivel 3.

    No esta implementado y no esta en `pipeline.DETECTORS`. La firma si esta
    alineada al contrato, por el mismo motivo que en `RandomForestDetector`:
    `predict(self, cube)` heredaba de `Detector.predict(self, cube, reference)`
    con un argumento menos, y la contradiccion solo se habria manifestado como
    un `TypeError` el dia que se escribiera el cuerpo.

    `higher_is_better` se hereda como `True`: el puntaje sera la abundancia
    fraccional del endmember objetivo, donde mayor es mas mineral. Es la
    direccion contraria a la del SAM, y es exactamente el caso que el contrato
    aprendio a manejar en la Semana 3.
    """

    def fit(self, cube: np.ndarray, reference: np.ndarray) -> UnmixingDetector:
        """Ajusta el conjunto de endmembers sobre la escena.

        **No es parte del contrato `Detector`**; ver la nota equivalente en
        `RandomForestDetector.fit`.

        Raises
        ------
        NotImplementedError
            Siempre. Nivel 3.
        """
        raise NotImplementedError

    def predict(self, cube: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """Mapa de abundancia fraccional del endmember, forma `(alto, ancho)`.

        Firma del contrato; ver `Detector.predict`.

        Raises
        ------
        NotImplementedError
            Siempre. Nivel 3.
        """
        raise NotImplementedError
