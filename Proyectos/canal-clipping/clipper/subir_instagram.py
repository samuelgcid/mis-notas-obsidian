"""Subida de Reels con la Instagram Graph API (subida reanudable, sin URL pública).

Requiere cuenta de Instagram profesional (Business/Creator) vinculada a una
página de Facebook, una app de Meta con `instagram_content_publish`, el ID de
usuario de IG en config.yaml (`instagram.ig_user_id`) y el token en
INSTAGRAM_ACCESS_TOKEN.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests


def subir(video: Path, textos: dict, privacidad: str, cfg: dict) -> str:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    ig = cfg["instagram"]["ig_user_id"]
    if not token or not ig:
        raise SystemExit("Faltan INSTAGRAM_ACCESS_TOKEN o instagram.ig_user_id (ver README).")
    if privacidad != "public":
        raise SystemExit("Instagram no tiene modo privado/oculto: usa --privacidad public para Reels.")
    v = cfg["instagram"]["version_api"]
    graph = f"https://graph.facebook.com/{v}"
    r = requests.post(f"{graph}/{ig}/media", timeout=60, data={
        "media_type": "REELS", "upload_type": "resumable", "caption": textos["caption"],
        "share_to_feed": "true", "access_token": token,
    })
    r.raise_for_status()
    contenedor = r.json()["id"]
    tam = video.stat().st_size
    with open(video, "rb") as f:
        requests.post(f"https://rupload.facebook.com/ig-api-upload/{v}/{contenedor}", data=f,
                      timeout=600, headers={"Authorization": f"OAuth {token}", "offset": "0",
                                            "file_size": str(tam)}).raise_for_status()
    for _ in range(60):
        estado = requests.get(f"{graph}/{contenedor}", timeout=30,
                              params={"fields": "status_code", "access_token": token}).json()
        if estado.get("status_code") == "FINISHED":
            break
        if estado.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram rechazó el vídeo: {estado}")
        time.sleep(5)
    pub = requests.post(f"{graph}/{ig}/media_publish", timeout=60,
                        data={"creation_id": contenedor, "access_token": token})
    pub.raise_for_status()
    return f"instagram media_id={pub.json()['id']}"
