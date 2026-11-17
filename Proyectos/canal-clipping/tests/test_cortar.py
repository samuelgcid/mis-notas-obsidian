import subprocess

import pytest
import yaml

from clipper import textos
from clipper.config import POR_DEFECTO
from clipper.cortar import a_segundos, cortar_todo, dimensiones, filtro_vertical


def _video(ruta, ancho, alto, seg=6):
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={ancho}x{alto}:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440", "-t", str(seg), "-c:v", "libx264",
        "-pix_fmt", "yuv420p", "-c:a", "aac", str(ruta)], check=True)


def test_a_segundos():
    assert a_segundos("01:02:03.5") == 3723.5
    assert a_segundos("2:30") == 150
    assert a_segundos(12) == 12


def test_filtro_recorte_respeta_centro():
    f = filtro_vertical(1920, 1080, "recorte", 0.0, 1080, 1920)
    assert f.startswith("crop=606:1080:0:0")
    assert ":1314:0" in filtro_vertical(1920, 1080, "recorte", 1.0, 1080, 1920)


@pytest.mark.parametrize("modo", ["recorte", "desenfoque"])
def test_corte_genera_vertical(tmp_path, modo):
    _video(tmp_path / "original.mp4", 1280, 720)
    plan = {"credito": "Clip de @x", "clips": [
        {"id": "01", "inicio": "00:00:01", "fin": "00:00:03.5", "titulo": "t", "modo": modo}]}
    (tmp_path / "clips.yaml").write_text(yaml.safe_dump(plan))
    cfg = dict(POR_DEFECTO, salida={"ancho": 360, "alto": 640, "crf": 30, "preset": "ultrafast"})
    [salida] = cortar_todo(tmp_path / "clips.yaml", cfg)
    assert dimensiones(salida) == (360, 640)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(salida)], capture_output=True, text=True).stdout)
    assert 2.3 < dur < 2.8


def test_rechaza_clip_demasiado_largo(tmp_path):
    _video(tmp_path / "original.mp4", 640, 360, seg=2)
    plan = {"clips": [{"id": "x", "inicio": 0, "fin": 500, "titulo": "t"}]}
    (tmp_path / "clips.yaml").write_text(yaml.safe_dump(plan))
    with pytest.raises(ValueError, match="dura"):
        cortar_todo(tmp_path / "clips.yaml", POR_DEFECTO)


def test_textos_exigen_credito():
    with pytest.raises(ValueError, match="credito"):
        textos.construir({}, {"titulo": "t"}, "youtube", POR_DEFECTO)
    t = textos.construir({"credito": "Clip de @x"}, {"titulo": "t", "hashtags": ["podcast"]},
                         "youtube", POR_DEFECTO)
    assert "Clip de @x" in t["descripcion"] and "#Shorts" in t["descripcion"]
    assert t["tags"] == ["podcast", "Shorts"]
