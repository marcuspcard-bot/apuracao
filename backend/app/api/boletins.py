from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Boletim, Resultado
from app.schemas.boletim import Confirmar, BoletimManual, LerFotos
from app.services.manual_service import save_manual, photos_preview
from app.services.photo_ocr import read_photo_text
from app.services.boletim_service import detail
from app.services.importacao_service import confirm_import, preview_pdf
from app.services.storage_service import StorageError, get_storage

router = APIRouter(prefix="/api/boletins", tags=["Boletins"])


@router.post("/preview")
def preview(
    file: UploadFile = File(...), substituir_id: UUID | None = None, db: Session = Depends(get_db)
):
    if file.content_type != "application/pdf" or not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "Envie um arquivo PDF com extensão .pdf e tipo application/pdf.")
    pdf = file.file.read(get_settings().max_pdf_size_mb * 1024 * 1024 + 1)
    if len(pdf) > get_settings().max_pdf_size_mb * 1024 * 1024:
        raise HTTPException(413, "O PDF excede o tamanho máximo permitido.")
    return preview_pdf(pdf, file.filename, db, substituir_id)


@router.post("/confirmar", status_code=201)
def confirmar(body: Confirmar, db: Session = Depends(get_db), storage=Depends(get_storage)):
    return confirm_import(body.preview_token, db, storage, body.substituir_id)


@router.post("/manual/confirmar", status_code=201)
def manual(body: BoletimManual, db: Session = Depends(get_db), storage=Depends(get_storage)):
    return save_manual(body, db, storage)


@router.post("/fotos/preview")
def fotos(files: list[UploadFile] = File(...)):
    return photos_preview(files)


@router.post("/fotos/ler")
def ler_fotos(body: LerFotos):
    return read_photo_text(body.foto_token)


@router.get("/{id}/fotos")
def fotos_url(id: UUID, db: Session = Depends(get_db), storage=Depends(get_storage)):
    b = find_boletim(id, db)
    bucket, path = b.evidencia_bucket, b.evidencia_path
    db.close()
    if not path:
        raise HTTPException(404, "Este boletim não possui fotos anexadas.")
    try:
        return {"url": storage.signed_url(bucket, path), "expires_in": 60}
    except StorageError as exc:
        raise HTTPException(502, "Não foi possível abrir as fotos. Tente novamente.") from exc


@router.get("/por-hash/{file_hash}")
def find_receipt(
    response: Response,
    file_hash: str = Path(pattern=r"^[a-f0-9]{64}$"),
    db: Session = Depends(get_db),
) -> dict[str, UUID] | None:
    response.headers["Cache-Control"] = "no-store"
    boletim_id = db.scalar(select(Boletim.id).where(Boletim.arquivo_hash == file_hash))
    return {"id": boletim_id} if boletim_id else None


@router.get("")
def list_boletins(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Boletim)
        .order_by(Boletim.created_at.desc(), Boletim.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        {
            key: getattr(b, key)
            for key in (
                "id",
                "origem",
                "municipio_nome",
                "municipio_codigo",
                "zona",
                "secao",
                "quantidade_secoes_agregadas",
                "total_secoes_representadas",
                "comparecimento",
                "created_at",
            )
        }
        for b in rows
    ]


def find_boletim(id: UUID, db: Session):
    b = db.scalar(
        select(Boletim)
        .where(Boletim.id == id)
        .options(
            selectinload(Boletim.secoes),
            selectinload(Boletim.resultados).selectinload(Resultado.candidatos),
        )
    )
    if not b:
        raise HTTPException(404, "Boletim não encontrado.")
    return b


@router.get("/{id}")
def get_boletim(id: UUID, db: Session = Depends(get_db)):
    return detail(find_boletim(id, db))


@router.get("/{id}/pdf")
def pdf_url(id: UUID, db: Session = Depends(get_db), storage=Depends(get_storage)):
    stored = db.execute(
        select(Boletim.storage_bucket, Boletim.storage_path).where(Boletim.id == id)
    ).first()
    db.close()
    if stored is None:
        raise HTTPException(404, "Boletim não encontrado.")
    if not stored.storage_path:
        raise HTTPException(404, "Lançamento manual sem PDF importado. Consulte as fotos anexadas.")
    try:
        return {
            "url": storage.signed_url(stored.storage_bucket, stored.storage_path),
            "expires_in": 60,
        }
    except StorageError as exc:
        raise HTTPException(502, "Não foi possível abrir o PDF original. Tente novamente.") from exc
