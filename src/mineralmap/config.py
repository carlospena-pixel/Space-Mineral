"""Carga y valida los YAML de configuracion -> objeto Config tipado."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Config:
    scene: dict[str, Any] = field(default_factory=dict)
    aoi: dict[str, Any] = field(default_factory=dict)
    preprocessing: dict[str, Any] = field(default_factory=dict)
    mineral: dict[str, Any] = field(default_factory=dict)
    algorithm: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)


def load_config(path: str | Path) -> Config:
    """Lee un YAML de configuracion (con soporte de `defaults:`) y devuelve un Config."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    defaults_name = raw.pop("defaults", None)
    if defaults_name:
        base = load_config(path.parent / defaults_name)
        merged = dict(base.__dict__)
        for key, value in raw.items():
            if isinstance(value, dict):
                merged[key] = {**merged.get(key, {}), **value}
            else:
                merged[key] = value
        raw = merged

    known_fields = Config.__dataclass_fields__
    return Config(**{k: v for k, v in raw.items() if k in known_fields})
