"""Carga de configuración (config.yaml) y rutas del proyecto."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
TRABAJO = RAIZ / "trabajo"
SECRETOS = RAIZ / "secretos"

POR_DEFECTO = {
    "privacidad_por_defecto": "private",  # private | unlisted | public
    "duracion_max_seg": 180,
    "salida": {"ancho": 1080, "alto": 1920, "crf": 20, "preset": "medium"},
    "youtube": {"categoria": "24", "hashtags_fijos": ["Shorts"]},
    "tiktok": {"privacidad": "SELF_ONLY"},
    "instagram": {"version_api": "v21.0", "ig_user_id": ""},
}


def _fusionar(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        out[k] = _fusionar(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def cargar_config(ruta: str | os.PathLike | None = None) -> dict:
    ruta = Path(ruta) if ruta else RAIZ / "config.yaml"
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    return _fusionar(POR_DEFECTO, datos or {})
