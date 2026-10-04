from io import BytesIO
import shutil
import subprocess

from PIL import Image, ImageDraw, ImageFont
import pytest

from app.services.preview_service import create_preview
from app.services.photo_ocr import read_photo_text
from fastapi import HTTPException


def image_pdf():
    image = Image.new("RGB", (1000, 350), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=38)
    draw.text((30, 40), "CANDIDATO 1234 VOTOS 52", fill="black", font=font)
    output = BytesIO()
    image.save(output, format="PDF")
    return output.getvalue()


def test_ocr_unavailable_keeps_manual_fallback(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(HTTPException) as exc:
        read_photo_text("x")
    assert exc.value.status_code == 503
    assert "digitação manual" in exc.value.detail


def test_ocr_timeout(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/tesseract")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("tesseract", 15)

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(HTTPException) as exc:
        read_photo_text(create_preview(image_pdf(), "fotos.pdf"))
    assert exc.value.status_code == 422


def test_real_ocr_text_is_only_a_suggestion():
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract not installed")
    languages = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, check=True
    ).stdout
    if b"por" not in languages:
        pytest.skip("Portuguese OCR data not installed")
    response = read_photo_text(create_preview(image_pdf(), "fotos.pdf"))
    assert "1234" in response["texto"]
    assert "52" in response["texto"]
    assert "Confira" in response["aviso"]
    assert "candidatos" not in response
