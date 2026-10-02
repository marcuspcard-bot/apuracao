import base64
import binascii
import logging
from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.locks import lock_keys
from app.models import TelaoCandidato
from app.services.storage_service import StorageError

MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PHOTO_PIXELS = 16_000_000
PHOTO_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
logger = logging.getLogger(__name__)


def prepare_photo(data_url: str) -> bytes:
    header, separator, encoded = data_url.partition(",")
    media_type = header.removeprefix("data:").removesuffix(";base64")
    if not separator or header != f"data:{media_type};base64" or media_type not in PHOTO_FORMATS:
        raise HTTPException(422, "Envie uma foto JPG, PNG ou WebP de até 2 MB.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, "Arquivo de foto inválido.") from exc
    if not content or len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(422, "A foto deve ter no máximo 2 MB.")
    try:
        with Image.open(BytesIO(content), formats=list(PHOTO_FORMATS.values())) as source:
            if source.format != PHOTO_FORMATS[media_type] or getattr(source, "is_animated", False):
                raise ValueError("Invalid image format")
            if source.width * source.height > MAX_PHOTO_PIXELS or min(source.size) < 64:
                raise ValueError("Invalid dimensions")
            source.load()
            oriented = ImageOps.exif_transpose(source)
            fitted = ImageOps.fit(oriented, (512, 512), method=Image.Resampling.LANCZOS)
            # Flatten transparency and discard metadata before persisting the portrait.
            rgba = fitted.convert("RGBA")
            clean = Image.new("RGB", (512, 512), "white")
            clean.paste(rgba, mask=rgba.getchannel("A"))
            output = BytesIO()
            clean.save(output, format="WEBP", quality=85, method=4)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            422, "Foto inválida. Use uma imagem estática de 64 pixels a 16 megapixels."
        ) from exc


def photo_url(candidate):
    if not candidate.foto_path:
        return None
    revision = candidate.foto_path.rsplit("/", 1)[-1].removesuffix(".webp")
    return f"/api/divulgacao/candidatos/{candidate.id}/foto?v={revision}"


def store_photo(storage, candidate, content: bytes, uploaded: list):
    bucket = get_settings().supabase_candidate_bucket
    if bucket == get_settings().supabase_storage_bucket:
        raise HTTPException(422, "Use um bucket de fotos separado do bucket de boletins.")
    path = f"telao/{candidate.id}/{uuid4().hex}.webp"
    # Keep the path even if the upload response is lost, for compensating cleanup.
    uploaded.append((bucket, path))
    storage.ensure_photo_bucket(bucket)
    storage.upload(bucket, path, content, content_type="image/webp")
    candidate.foto_bucket, candidate.foto_path = bucket, path


def discard_photos(storage, photos):
    for bucket, path in photos:
        try:
            storage.delete(bucket, path)
        except StorageError:
            logger.warning("Foto sem referência não removida: %s/%s", bucket, path)


def discard_uncommitted_photos(db, storage, uploaded):
    if not uploaded:
        return
    # A failed commit response can hide a successful commit. Recheck under the config lock.
    try:
        db.rollback()
        with db.begin():
            lock_keys(db, ["telao-config:1"])
            for bucket, path in uploaded:
                referenced = db.scalar(
                    select(TelaoCandidato.id).where(
                        TelaoCandidato.foto_bucket == bucket,
                        TelaoCandidato.foto_path == path,
                    )
                )
                if referenced is None:
                    discard_photos(storage, [(bucket, path)])
    except Exception:
        logger.warning("Não foi possível conferir fotos após falha; arquivos preservados.")
