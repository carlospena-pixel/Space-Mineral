"""Detectores supervisados: aprenden de la verdad de terreno en vez de una firma.

`Detector.predict(cube, reference)` esta pensado para reglas espectrales como
SAM. Un modelo supervisado no necesita firma pero si un paso de aprendizaje,
asi que `SupervisedDetector`:

- agrega `fit(features, y, valid)`, que aprende SOLO de los pixeles 0/1 de `y`
  con todas las entradas finitas (los 255 y los NaN se descartan siempre);
- implementa `predict(cube, reference=None)`: ignora la firma y devuelve la
  probabilidad (o el puntaje) de positivo, mayor es mejor, NaN sin dato;
- ofrece `fit_table` / `score_table` para trabajar con tablas de pixeles, que
  es como corre la validacion cruzada.

No se registran en `pipeline.DETECTORS`: el pipeline no sabe entrenar y no se
toca. Los usa `scripts/comparar_modelos.py`.
"""

from __future__ import annotations

from abc import abstractmethod

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from mineralmap.algorithms.base import Detector


class SupervisedDetector(Detector):
    """Contrato comun de los detectores que se entrenan con la verdad."""

    higher_is_better = True
    bands = None

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.model_ = None

    @abstractmethod
    def _build(self, y: np.ndarray):
        """Devuelve el estimador sin entrenar; `y` sirve para pesar clases."""

    # --- tablas (n_pixeles, n_entradas) -------------------------------------
    def fit_table(self, X: np.ndarray, y: np.ndarray) -> SupervisedDetector:
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y)
        if X.ndim != 2 or X.shape[0] != y.shape[0]:
            raise ValueError(f"X {X.shape} e y {y.shape} no calzan.")
        if not np.isfinite(X).all():
            raise ValueError("fit_table recibio entradas no finitas; filtralas antes.")
        if not np.isin(y, (0, 1)).all():
            raise ValueError("fit_table solo acepta etiquetas 0 y 1 (nunca 255).")
        if len(np.unique(y)) < 2:
            raise ValueError("Hacen falta positivos y negativos para entrenar.")
        self.model_ = self._build(y.astype(int))
        self.model_.fit(X, y.astype(int))
        return self

    def score_table(self, X: np.ndarray) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("El detector no esta entrenado; llama fit antes.")
        X = np.asarray(X, dtype=np.float64)
        salida = np.full(X.shape[0], np.nan)
        ok = np.all(np.isfinite(X), axis=1)
        if ok.any():
            salida[ok] = self._score(X[ok])
        return salida

    def _score(self, X: np.ndarray) -> np.ndarray:
        if hasattr(self.model_, "predict_proba"):
            return self.model_.predict_proba(X)[:, 1]
        return self.model_.decision_function(X)

    # --- cubos (n_entradas, alto, ancho) -------------------------------------
    def fit(
        self, features: np.ndarray, y: np.ndarray, valid: np.ndarray | None = None
    ) -> SupervisedDetector:
        """Aprende de los pixeles con `y` en {0, 1}, entradas finitas y `valid`."""
        n = features.shape[0]
        X = features.reshape(n, -1).T
        etiquetas = np.asarray(y, dtype=np.float64).ravel()
        usar = np.isin(etiquetas, (0, 1)) & np.all(np.isfinite(X), axis=1)
        if valid is not None:
            usar &= np.asarray(valid, dtype=bool).ravel()
        return self.fit_table(X[usar], etiquetas[usar].astype(int))

    def predict(self, cube: np.ndarray, reference: np.ndarray | None = None) -> np.ndarray:
        n, alto, ancho = cube.shape
        return self.score_table(cube.reshape(n, -1).T).reshape(alto, ancho)


class LogisticDetector(SupervisedDetector):
    def __init__(self, C: float = 1.0, seed: int = 42):
        super().__init__(seed)
        self.C = C

    def _build(self, y):
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(C=self.C, class_weight="balanced", max_iter=5000),
        )


class KNNDetector(SupervisedDetector):
    """K vecinos sobre entradas estandarizadas. Puntaje = fraccion de vecinos
    positivos; KNN no admite pesos de clase, pero el AUC no depende del corte."""

    def __init__(self, k: int = 15, seed: int = 42):
        super().__init__(seed)
        self.k = k

    def _build(self, y):
        return make_pipeline(
            StandardScaler(), KNeighborsClassifier(n_neighbors=min(self.k, len(y)))
        )


class SVMDetector(SupervisedDetector):
    """SVM de kernel RBF; puntaje = distancia firmada al hiperplano."""

    def __init__(self, C: float = 1.0, seed: int = 42):
        super().__init__(seed)
        self.C = C

    def _build(self, y):
        return make_pipeline(
            StandardScaler(),
            SVC(C=self.C, kernel="rbf", gamma="scale", class_weight="balanced"),
        )

    def _score(self, X):
        return self.model_.decision_function(X)


class HistGradientBoostingDetector(SupervisedDetector):
    def __init__(self, learning_rate: float = 0.1, seed: int = 42):
        super().__init__(seed)
        self.learning_rate = learning_rate

    def _build(self, y):
        return HistGradientBoostingClassifier(
            learning_rate=self.learning_rate,
            class_weight="balanced",
            random_state=self.seed,
        )


class XGBoostDetector(SupervisedDetector):
    def __init__(self, max_depth: int = 6, seed: int = 42):
        super().__init__(seed)
        self.max_depth = max_depth

    def _build(self, y):
        from xgboost import XGBClassifier

        n_pos = int((y == 1).sum())
        n_neg = int((y == 0).sum())
        return XGBClassifier(
            n_estimators=300,
            max_depth=self.max_depth,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=n_neg / max(n_pos, 1),
            tree_method="hist",
            random_state=self.seed,
            n_jobs=4,
            eval_metric="logloss",
        )
