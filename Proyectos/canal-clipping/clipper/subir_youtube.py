"""Subida a YouTube (Shorts) con la YouTube Data API v3.

Una sola vez: `python -m clipper auth youtube` abre el navegador, das permiso
y se guarda `secretos/youtube_token.json` (no se versiona).
"""
from __future__ import annotations

from pathlib import Path

from .config import SECRETOS

ALCANCES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENTE = SECRETOS / "youtube_client_secret.json"
TOKEN = SECRETOS / "youtube_token.json"


def autorizar() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENTE.exists():
        raise SystemExit(f"Falta {CLIENTE} (descárgalo de Google Cloud Console, ver README).")
    cred = InstalledAppFlow.from_client_secrets_file(str(CLIENTE), ALCANCES).run_local_server(port=0)
    TOKEN.write_text(cred.to_json(), encoding="utf-8")
    print(f"Token guardado en {TOKEN}")


def _servicio():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not TOKEN.exists():
        raise SystemExit("No hay token de YouTube. Ejecuta: python -m clipper auth youtube")
    cred = Credentials.from_authorized_user_file(str(TOKEN), ALCANCES)
    if not cred.valid:
        cred.refresh(Request())
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=cred, cache_discovery=False)


def subir(video: Path, textos: dict, privacidad: str, cfg: dict) -> str:
    from googleapiclient.http import MediaFileUpload

    cuerpo = {
        "snippet": {
            "title": textos["titulo"],
            "description": textos["descripcion"],
            "tags": textos["tags"],
            "categoryId": cfg["youtube"]["categoria"],
        },
        "status": {"privacyStatus": privacidad, "selfDeclaredMadeForKids": False},
    }
    peticion = _servicio().videos().insert(
        part="snippet,status", body=cuerpo,
        media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=-1, resumable=True),
    )
    respuesta = None
    while respuesta is None:
        _, respuesta = peticion.next_chunk()
    return f"https://youtube.com/shorts/{respuesta['id']}"
