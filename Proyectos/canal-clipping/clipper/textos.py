"""Construye título/descripción por plataforma a partir de clips.yaml (siempre con crédito)."""
from __future__ import annotations


def _hashtags(lista) -> str:
    return " ".join("#" + h.lstrip("#").replace(" ", "") for h in lista or [])


def construir(plan: dict, clip: dict, plataforma: str, cfg: dict) -> dict:
    credito = plan.get("credito", "").strip()
    if not credito:
        raise ValueError("Falta 'credito' en clips.yaml: hay que citar siempre al creador original.")
    tags = list(clip.get("hashtags", []))
    if plataforma == "youtube":
        tags += [t for t in cfg["youtube"]["hashtags_fijos"] if t not in tags]
    cuerpo = "\n\n".join(p for p in [clip.get("descripcion", "").strip(), credito, _hashtags(tags)] if p)
    titulo = clip["titulo"].strip()
    if plataforma == "youtube":
        return {"titulo": titulo[:100], "descripcion": cuerpo[:5000], "tags": [t.lstrip("#") for t in tags]}
    # TikTok e Instagram solo tienen un campo de texto (caption)
    return {"caption": f"{titulo}\n\n{cuerpo}"[:2200]}
