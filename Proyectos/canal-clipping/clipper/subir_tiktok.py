"""Subida a TikTok con la Content Posting API (Direct Post, FILE_UPLOAD).

Requiere una app en developers.tiktok.com con el producto "Content Posting API"
y el permiso `video.publish`. Mientras la app no pase la auditoría de TikTok,
solo puede publicar en privado (SELF_ONLY).
Token de acceso de usuario en la variable TIKTOK_ACCESS_TOKEN.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2/post/publish"


def _cabeceras() -> dict:
    token = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if not token:
        raise SystemExit("Falta TIKTOK_ACCESS_TOKEN (ver README).")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}


def subir(video: Path, textos: dict, privacidad: str, cfg: dict) -> str:
    tam = video.stat().st_size
    if tam > 64 * 1024 * 1024:
        raise ValueError("Clip > 64 MB: baja la calidad (crf) o acórtalo.")
    nivel = cfg["tiktok"]["privacidad"] if privacidad != "public" else "PUBLIC_TO_EVERYONE"
    r = requests.post(f"{API}/video/init/", headers=_cabeceras(), timeout=60, json={
        "post_info": {"title": textos["caption"], "privacy_level": nivel,
                      "disable_duet": False, "disable_comment": False, "disable_stitch": False},
        "source_info": {"source": "FILE_UPLOAD", "video_size": tam, "chunk_size": tam,
                        "total_chunk_count": 1},
    })
    r.raise_for_status()
    datos = r.json()["data"]
    with open(video, "rb") as f:
        requests.put(datos["upload_url"], data=f, timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(tam),
            "Content-Range": f"bytes 0-{tam - 1}/{tam}",
        }).raise_for_status()
    for _ in range(60):
        e = requests.post(f"{API}/status/fetch/", headers=_cabeceras(), timeout=30,
                          json={"publish_id": datos["publish_id"]}).json()["data"]
        if e.get("status") == "PUBLISH_COMPLETE":
            return f"tiktok publish_id={datos['publish_id']}"
        if e.get("status") == "FAILED":
            raise RuntimeError(f"TikTok rechazó el vídeo: {e.get('fail_reason')}")
        time.sleep(5)
    return f"tiktok publish_id={datos['publish_id']} (procesando)"
