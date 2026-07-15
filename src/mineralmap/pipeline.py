"""Orquestador: encadena los pasos (preprocessing -> spectral -> algorithms ->
validation -> visualization) segun lo definido en un Config.

Es el unico lugar donde se ve el flujo completo.
"""

from __future__ import annotations

from mineralmap.config import Config


def run_pipeline(config: Config) -> None:
    raise NotImplementedError
