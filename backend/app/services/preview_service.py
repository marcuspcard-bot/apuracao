import base64
import json
import re

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException

from app.core.config import get_settings


def safe_filename(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    return re.sub(r"[^\w.() -]", "_", name)[:240] or "boletim.pdf"


def create_preview(file_bytes: bytes, filename: str) -> str:
    # Stateless authenticated encryption: no permanent PDF storage before confirmation.
    payload = json.dumps(
        {"pdf": base64.b64encode(file_bytes).decode(), "filename": filename}
    ).encode()
    return Fernet(get_settings().preview_secret_key).encrypt(payload).decode()


def recover_preview(token: str) -> tuple[bytes, str]:
    settings = get_settings()
    try:
        payload = json.loads(
            Fernet(settings.preview_secret_key).decrypt(
                token.encode(), ttl=settings.preview_ttl_seconds
            )
        )
        pdf = base64.b64decode(payload["pdf"], validate=True)
        if len(pdf) > settings.max_pdf_size_mb * 1024 * 1024:
            raise ValueError("size")
        return pdf, safe_filename(payload["filename"])
    except (InvalidToken, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(410, "Prévia inválida ou expirada. Envie o PDF novamente.") from exc
