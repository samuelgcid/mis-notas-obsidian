"""Paso 1: traer el vídeo largo (URL con yt-dlp o archivo local) a trabajo/<id>/."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .config import TRABAJO


def _id_trabajo(origen: str) -> str:
    return hashlib.sha1(origen.encode()).hexdigest()[:10]


def preparar(origen: str) -> Path:
    """Devuelve la carpeta del trabajo con `original.mp4` e `info.json`."""
    carpeta = TRABAJO / _id_trabajo(origen)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / "original.mp4"
    info_path = carpeta / "info.json"
    if destino.exists():
        return carpeta

    local = Path(origen).expanduser()
    if local.exists():
        shutil.copy2(local, destino)
        info = {"origen": str(local), "titulo": local.stem, "canal": "", "url": ""}
    else:
        import yt_dlp

        opciones = {
            "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b",
            "merge_output_format": "mp4",
            "outtmpl": str(carpeta / "original.%(ext)s"),
            "quiet": True,
            "noprogress": True,
        }
        with yt_dlp.YoutubeDL(opciones) as ydl:
            meta = ydl.extract_info(origen, download=True)
        info = {
            "origen": origen,
            "url": meta.get("webpage_url", origen),
            "titulo": meta.get("title", ""),
            "canal": meta.get("uploader") or meta.get("channel", ""),
            "canal_url": meta.get("uploader_url") or meta.get("channel_url", ""),
            "duracion": meta.get("duration"),
        }
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    return carpeta
