"""Comparacion entre mapas: umbral comun, AUC por grupo y empate por bloques."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score


def top_threshold(
    valores: np.ndarray, fraccion: float, higher_is_better: bool
) -> tuple[float, str]:
    """Umbral que marca la `fraccion` mejor puntuada, y la regla que se uso.

    Si ese corte cae en el peor valor (mapas con mayoria de ceros, como los de
    EMIT L2B), marcaria todo: se usa el menor valor que lo supera, o sea
    "mineral identificado".
    """
    v = np.asarray(valores)
    s = v if higher_is_better else -v
    corte, regla = np.quantile(s, 1 - fraccion), "top"
    fondo = np.min(s)
    if corte <= fondo and np.any(s > fondo):
        corte, regla = np.min(s[s > fondo]), "identificado"
    return float(corte if higher_is_better else -corte), regla


def group_auc(
    puntaje: np.ndarray, verdad: np.ndarray, validos: np.ndarray, grupo: np.ndarray
) -> float:
    """AUC de los positivos de `grupo` contra todos los negativos validos.

    `puntaje` viene orientado: mayor es mejor.
    """
    pos = validos & (verdad == 1) & grupo
    neg = validos & (verdad == 0)
    if not pos.any() or not neg.any():
        return float("nan")
    y = np.r_[np.ones(pos.sum()), np.zeros(neg.sum())]
    return float(roc_auc_score(y, np.r_[puntaje[pos], puntaje[neg]]))


def block_bootstrap_ties(
    puntajes: dict[str, np.ndarray],
    y: np.ndarray,
    bloques: np.ndarray,
    n_sorteos: int = 500,
    semilla: int = 42,
) -> tuple[str, dict[str, dict]]:
    """Que modelos empatan con el de mayor AUC, sorteando bloques con reemplazo.

    Hay empate si el intervalo del 95 % de la diferencia de AUC con el mejor
    incluye el 0. Este margen es una definicion del equipo: el Charter no fija
    una. `puntajes` viene orientado (mayor es mejor) y alineado con `y`.
    """
    auc = {n: float(roc_auc_score(y, s)) for n, s in puntajes.items()}
    mejor = max(auc, key=auc.get)
    ids = np.unique(bloques)
    por_bloque = {b: np.flatnonzero(bloques == b) for b in ids}
    rng = np.random.default_rng(semilla)
    difs: dict[str, list[float]] = {n: [] for n in puntajes}
    for _ in range(n_sorteos):
        sorteo = rng.choice(ids, ids.size, replace=True)
        idx = np.concatenate([por_bloque[b] for b in sorteo])
        if y[idx].min() == y[idx].max():
            continue
        auc_mejor = roc_auc_score(y[idx], puntajes[mejor][idx])
        for nombre, s in puntajes.items():
            difs[nombre].append(auc_mejor - roc_auc_score(y[idx], s[idx]))

    salida = {}
    for nombre in puntajes:
        bajo, alto = np.percentile(difs[nombre], [2.5, 97.5])
        salida[nombre] = {
            "auc": auc[nombre],
            "ic95": [float(bajo), float(alto)],
            "empate": bool(bajo <= 0),
        }
    return mejor, salida
