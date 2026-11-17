"""Paso 2: transcripción con marcas de tiempo para elegir los mejores momentos.

Genera `transcripcion.txt` (una línea por segmento, `[hh:mm:ss.s → hh:mm:ss.s] texto`),
que es lo que Claude lee para proponer `clips.yaml`.
"""
from __future__ import annotations

import json
from pathlib import Path


def fmt(seg: float) -> str:
    h, resto = divmod(seg, 3600)
    m, s = divmod(resto, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:04.1f}"


def transcribir(carpeta: Path, modelo: str = "small", idioma: str | None = None) -> Path:
    from faster_whisper import WhisperModel

    salida_txt = carpeta / "transcripcion.txt"
    if salida_txt.exists():
        return salida_txt
    wm = WhisperModel(modelo, device="auto", compute_type="int8")
    segmentos, info = wm.transcribe(str(carpeta / "original.mp4"), language=idioma, vad_filter=True)
    filas = [{"inicio": s.start, "fin": s.end, "texto": s.text.strip()} for s in segmentos]
    (carpeta / "transcripcion.json").write_text(
        json.dumps({"idioma": info.language, "segmentos": filas}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    salida_txt.write_text(
        "\n".join(f"[{fmt(f['inicio'])} → {fmt(f['fin'])}] {f['texto']}" for f in filas) + "\n",
        encoding="utf-8",
    )
    return salida_txt
