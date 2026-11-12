"""Particion "dejar una familia de roca fuera" para validar generalizacion.

La validacion cruzada por bloques mezclaba familias: el 93 % de sus positivos
era del Complejo Yabricoya, y un AUC alto media sobre todo "encontrar
Yabricoya". Esta particion pregunta otra cosa: si un modelo entrenado sin una
familia la encuentra igual.

Para cada familia F:
  - prueba = bloques que contienen positivos de F;
  - positivos de prueba = positivos de F (siempre dentro de esos bloques);
  - negativos de prueba = negativos de esos mismos bloques;
  - entrenamiento = pixeles etiquetados (0/1) de TODOS los demas bloques.
Los positivos de otras familias que caen en bloques de prueba no se usan ni
para entrenar ni para medir.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class FamilySplit:
    familia: str
    bloques_prueba: list[int]
    entrenamiento: np.ndarray  # bool (alto, ancho)
    prueba_pos: np.ndarray  # bool
    prueba_neg: np.ndarray  # bool

    @property
    def n_pos(self) -> int:
        return int(self.prueba_pos.sum())

    @property
    def n_neg(self) -> int:
        return int(self.prueba_neg.sum())


def block_ids(forma: tuple[int, int], bloque_px: int) -> np.ndarray:
    """Id de bloque por pixel: fila_de_bloque * n_columnas + columna_de_bloque."""
    alto, ancho = forma
    filas, cols = np.indices(forma)
    n_cols = -(-ancho // bloque_px)
    return (filas // bloque_px) * n_cols + cols // bloque_px


def leave_one_family_out(
    verdad: np.ndarray,
    familia: np.ndarray,
    nombres: dict[int, str],
    bloques: np.ndarray,
    valido: np.ndarray,
) -> list[FamilySplit]:
    """Una particion por familia.

    Parameters
    ----------
    verdad:
        1 positivo, 0 negativo, otro valor = no se usa (255, NaN).
    familia:
        Codigo de familia por pixel (0 = sin familia). Solo importa en positivos.
    nombres:
        Codigo -> nombre de familia.
    bloques:
        Id de bloque por pixel.
    valido:
        Pixeles con entradas validas.

    Raises
    ------
    ValueError
        Si hay positivos sin familia: no se podrian asignar a ninguna vuelta y
        se colarian en el entrenamiento de todas.
    """
    v = np.asarray(verdad)
    pos = (v == 1) & valido
    neg = (v == 0) & valido
    sin_familia = pos & (familia == 0)
    if sin_familia.any():
        raise ValueError(f"{int(sin_familia.sum())} positivos no tienen familia asignada.")

    salida = []
    for codigo, nombre in nombres.items():
        de_f = pos & (familia == codigo)
        bloques_f = sorted(np.unique(bloques[de_f]).tolist())
        en_prueba = np.isin(bloques, bloques_f)
        entrenamiento = (pos | neg) & ~en_prueba
        salida.append(FamilySplit(
            familia=nombre,
            bloques_prueba=bloques_f,
            entrenamiento=entrenamiento,
            prueba_pos=de_f,
            prueba_neg=neg & en_prueba,
        ))
    return salida


def is_evaluable(split: FamilySplit, min_pixeles: int, min_bloques: int) -> bool:
    """Suficientes positivos y replica espacial para reportar un AUC."""
    return split.n_pos >= min_pixeles and len(split.bloques_prueba) >= min_bloques and split.n_neg > 0
