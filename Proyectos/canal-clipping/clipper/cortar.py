"""Paso 3: cortar los momentos elegidos y pasarlos a vertical 9:16.

Modos por clip:
- `recorte` (por defecto): recorta una franja 9:16 del vídeo. `centro_x` (0–1)
  desplaza la franja a izquierda/derecha para seguir a quien habla.
- `desenfoque`: el vídeo entero centrado, con el mismo vídeo ampliado y
  desenfocado de fondo. Útil cuando hay dos personas en plano.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from .config import cargar_config


def a_segundos(t) -> float:
    if isinstance(t, (int, float)):
        return float(t)
    partes = [float(p) for p in str(t).strip().split(":")]
    seg = 0.0
    for p in partes:
        seg = seg * 60 + p
    return seg


def dimensiones(video: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "json", str(video)],
        check=True, capture_output=True, text=True,
    ).stdout
    s = json.loads(out)["streams"][0]
    return int(s["width"]), int(s["height"])


def filtro_vertical(ancho: int, alto: int, modo: str, centro_x: float, W: int, H: int) -> str:
    if ancho / alto <= W / H:  # ya es vertical o más estrecho: escalar y rellenar
        return (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1")
    if modo == "desenfoque":
        return (f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},boxblur=20:2[fondo];"
                f"[b]scale={W}:-2[frente];[fondo][frente]overlay=0:(H-h)/2,setsar=1")
    cx = min(max(float(centro_x), 0.0), 1.0)
    franja = int(alto * W / H) // 2 * 2
    x = int((ancho - franja) * cx)
    return f"crop={franja}:{alto}:{x}:0,scale={W}:{H},setsar=1"


def cortar_clip(fuente: Path, clip: dict, destino: Path, cfg: dict) -> Path:
    ini, fin = a_segundos(clip["inicio"]), a_segundos(clip["fin"])
    if fin <= ini:
        raise ValueError(f"Clip {clip.get('id')}: 'fin' debe ser mayor que 'inicio'")
    if fin - ini > cfg["duracion_max_seg"]:
        raise ValueError(f"Clip {clip.get('id')}: dura {fin - ini:.0f}s (> {cfg['duracion_max_seg']}s)")
    ancho, alto = dimensiones(fuente)
    s = cfg["salida"]
    vf = filtro_vertical(ancho, alto, clip.get("modo", "recorte"), clip.get("centro_x", 0.5),
                         s["ancho"], s["alto"])
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-ss", f"{ini:.3f}", "-i", str(fuente), "-t", f"{fin - ini:.3f}",
        "-filter_complex" if ";" in vf else "-vf", vf,
        "-c:v", "libx264", "-preset", s["preset"], "-crf", str(s["crf"]), "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
        str(destino),
    ]
    subprocess.run(cmd, check=True)
    return destino


def cortar_todo(clips_yaml: Path, cfg: dict | None = None) -> list[Path]:
    cfg = cfg or cargar_config()
    plan = yaml.safe_load(clips_yaml.read_text(encoding="utf-8"))
    carpeta = clips_yaml.parent
    fuente = carpeta / plan.get("fuente", "original.mp4")
    (carpeta / "clips").mkdir(exist_ok=True)
    hechos = []
    for clip in plan["clips"]:
        destino = carpeta / "clips" / f"{clip['id']}.mp4"
        cortar_clip(fuente, clip, destino, cfg)
        hechos.append(destino)
        print(f"✔ {destino.relative_to(carpeta)}")
    return hechos
