"""Optional OCR assistance. Never turn unreviewed text into electoral results."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf
from fastapi import HTTPException

from app.services.preview_service import recover_preview


def read_photo_text(token):
    binary = shutil.which("tesseract")
    if binary is None:
        raise HTTPException(
            503,
            "A leitura de texto por foto não está disponível neste servidor. Você pode continuar pela digitação manual.",
        )
    pdf, _ = recover_preview(token)
    deadline = time.monotonic() + 45
    texts = []
    try:
        with (
            pymupdf.open(stream=pdf, filetype="pdf") as doc,
            TemporaryDirectory(prefix="bu-ocr-") as folder,
        ):
            if not 1 <= len(doc) <= 10:
                raise HTTPException(422, "A leitura aceita até dez páginas de fotos.")
            for index, page in enumerate(doc):
                if page.rect.width <= 0 or page.rect.height <= 0:
                    raise ValueError("empty page")
                scale = min(2, (10000000 / (page.rect.width * page.rect.height)) ** 0.5)
                image = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                path = Path(folder) / "pagina.png"
                image.save(str(path))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(binary, 45)
                result = subprocess.run(
                    [binary, str(path), "stdout", "-l", "por", "--psm", "6"],
                    capture_output=True,
                    timeout=min(15, remaining),
                    check=True,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1"},
                )
                text = result.stdout.decode("utf-8", errors="replace").strip()
                if text:
                    texts.append(f"Foto {index + 1}\n{text[:30000]}")
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            422,
            "A leitura demorou demais. Tente uma foto mais nítida ou continue digitando os votos.",
        ) from exc
    except (subprocess.CalledProcessError, OSError) as exc:
        raise HTTPException(
            503,
            "Não foi possível reconhecer o texto. Confira se o servidor possui Tesseract com o idioma português.",
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            422, "Não foi possível ler as imagens. Envie as fotos novamente."
        ) from exc
    return {
        "texto": "\n\n".join(texts),
        "aviso": "Texto reconhecido automaticamente. Confira os números na foto antes de digitar e salvar os votos.",
    }
