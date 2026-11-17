"""CLI del canal de clipping.

  python -m clipper preparar <url|archivo> [--modelo small] [--idioma es]
  python -m clipper cortar trabajo/<id>/clips.yaml
  python -m clipper subir trabajo/<id>/clips.yaml --plataformas youtube,tiktok,instagram [--privacidad private]
  python -m clipper auth youtube
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from . import textos
from .config import cargar_config

SUBIDORES = {
    "youtube": "subir_youtube",
    "tiktok": "subir_tiktok",
    "instagram": "subir_instagram",
}


def cmd_preparar(a):
    from .descargar import preparar
    from .transcribir import transcribir

    carpeta = preparar(a.origen)
    print(f"Vídeo en {carpeta / 'original.mp4'}")
    if not a.sin_transcripcion:
        print(f"Transcripción en {transcribir(carpeta, a.modelo, a.idioma)}")
    print(f"Siguiente paso: escribir {carpeta / 'clips.yaml'} (ver clips.example.yaml)")


def cmd_cortar(a):
    from .cortar import cortar_todo

    cortar_todo(Path(a.clips_yaml), cargar_config(a.config))


def cmd_subir(a):
    import importlib

    cfg = cargar_config(a.config)
    ruta = Path(a.clips_yaml)
    plan = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    registro_path = ruta.parent / "subidas.json"
    registro = json.loads(registro_path.read_text()) if registro_path.exists() else {}
    privacidad = a.privacidad or cfg["privacidad_por_defecto"]
    for plataforma in [p.strip() for p in a.plataformas.split(",") if p.strip()]:
        modulo = importlib.import_module(f".{SUBIDORES[plataforma]}", __package__)
        for clip in plan["clips"]:
            clave = f"{plataforma}:{clip['id']}"
            if clave in registro:
                print(f"= {clave} ya subido: {registro[clave]}")
                continue
            video = ruta.parent / "clips" / f"{clip['id']}.mp4"
            if not video.exists():
                raise SystemExit(f"No existe {video}: ejecuta antes `cortar`.")
            enlace = modulo.subir(video, textos.construir(plan, clip, plataforma, cfg), privacidad, cfg)
            registro[clave] = enlace
            registro_path.write_text(json.dumps(registro, indent=2, ensure_ascii=False))
            print(f"↑ {clave} → {enlace}")


def cmd_auth(a):
    if a.plataforma != "youtube":
        raise SystemExit("TikTok e Instagram usan tokens en variables de entorno (ver README).")
    from .subir_youtube import autorizar

    autorizar()


def main(argv=None):
    p = argparse.ArgumentParser(prog="clipper")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("preparar")
    s.add_argument("origen")
    s.add_argument("--modelo", default="small")
    s.add_argument("--idioma", default=None)
    s.add_argument("--sin-transcripcion", action="store_true")
    s.set_defaults(f=cmd_preparar)

    s = sub.add_parser("cortar")
    s.add_argument("clips_yaml")
    s.set_defaults(f=cmd_cortar)

    s = sub.add_parser("subir")
    s.add_argument("clips_yaml")
    s.add_argument("--plataformas", default="youtube")
    s.add_argument("--privacidad", choices=["private", "unlisted", "public"], default=None)
    s.set_defaults(f=cmd_subir)

    s = sub.add_parser("auth")
    s.add_argument("plataforma", choices=list(SUBIDORES))
    s.set_defaults(f=cmd_auth)

    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
