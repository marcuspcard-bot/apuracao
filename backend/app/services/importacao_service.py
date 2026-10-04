import logging
from datetime import datetime, timezone
from fastapi.encoders import jsonable_encoder

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Boletim
from app.schemas.boletim import BoletimDados
from app.services.boletim_service import make_boletim, detail
from app.services.bu_parser import parse_bu_text
from app.services.duplicate_checker import check_hash, check_sections, lock_scope
from app.services.file_hash import calculate_sha256
from app.services.pdf_processing import PdfProcessingError, read_pdf_text
from app.services.preview_service import create_preview, recover_preview, safe_filename
from app.services.storage_service import StorageError
from app.services.validator import validate_bu

logger = logging.getLogger(__name__)


def parse_pdf(pdf: bytes) -> BoletimDados:
    try:
        text = read_pdf_text(pdf)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except PdfProcessingError as exc:
        raise HTTPException(503, str(exc), headers={"Retry-After": "2"}) from exc
    try:
        return parse_bu_text(text)
    except ValueError as exc:
        raise HTTPException(422, {"status": "INCONSISTENTE", "problemas": [str(exc)]}) from exc


def replacement_target(db, data, target_id):
    old = db.scalar(select(Boletim).where(Boletim.id == target_id).with_for_update())
    if old is None:
        raise HTTPException(409, "O lançamento manual não existe mais. Atualize a listagem.")
    if old.origem != "MANUAL":
        raise HTTPException(409, "Somente um lançamento manual pode ser substituído.")
    identity = (
        old.eleicao_data,
        old.eleicao_turno,
        int(old.municipio_codigo),
        int(old.zona),
        int(old.secao),
    )
    incoming = (
        data.eleicao.data,
        data.eleicao.turno,
        int(data.municipio.codigo),
        int(data.zona),
        int(data.secao),
    )
    if identity != incoming or {int(s.numero_secao) for s in old.secoes} != {
        int(data.secao),
        *map(int, data.secoes_agregadas),
    }:
        raise HTTPException(
            422,
            "O PDF deve corresponder à mesma eleição, município, zona, seção principal e seções agregadas do lançamento manual.",
        )
    imported = {
        c.nome: {int(v.numero) for v in c.candidatos}
        | {int(v.numero) for seat in c.vagas for v in seat.candidatos}
        for c in data.cargos
    }
    for result in old.resultados:
        if result.cargo not in imported or any(
            int(c.numero_candidato) not in imported[result.cargo] for c in result.candidatos
        ):
            raise HTTPException(
                422,
                "O PDF não identifica todos os candidatos digitados. Confira o documento antes de substituir.",
            )
    return old


def preview_pdf(pdf: bytes, filename: str, db: Session, substituir_id=None):
    file_hash = calculate_sha256(pdf)
    try:
        check_hash(db, file_hash)
    finally:
        # No connection is needed while reading/encrypting the PDF.
        db.close()
    data = parse_pdf(pdf)
    problems = validate_bu(data)
    filename = safe_filename(filename)
    previous = None
    if substituir_id:
        try:
            previous = detail(replacement_target(db, data, substituir_id))
        finally:
            db.close()
    return {
        "substituicao": previous,
        "status": "INCONSISTENTE" if problems else "OK",
        "hash": file_hash,
        "arquivo_nome": filename,
        "dados": data,
        "problemas": problems,
        "preview_token": create_preview(pdf, filename),
        "expires_in": get_settings().preview_ttl_seconds,
    }


def _recover_upload(db, data, file_hash, bucket, path, storage):
    # An interrupted COMMIT may have succeeded. Never delete its PDF without checking.
    try:
        with db.begin():
            lock_scope(db, data, file_hash)
            existing_id = db.scalar(select(Boletim.id).where(Boletim.arquivo_hash == file_hash))
            if existing_id:
                return existing_id
            storage.delete(bucket, path)
    except (StorageError, SQLAlchemyError):
        logger.exception("Falha na compensação do storage: bucket=%s path=%s", bucket, path)
    return None


def confirm_import(token: str, db: Session, storage, substituir_id=None):
    pdf, filename = recover_preview(token)
    file_hash = calculate_sha256(pdf)
    data = parse_pdf(pdf)
    problems = validate_bu(data)
    if problems:
        raise HTTPException(422, {"status": "INCONSISTENTE", "problemas": problems})
    bucket = get_settings().supabase_storage_bucket
    path = (
        f"{data.eleicao.data.year}/turno-{data.eleicao.turno}/{data.municipio.codigo}/"
        f"{data.zona}/{data.secao}/{file_hash}.pdf"
    )
    uploaded = False
    try:
        with db.begin():
            lock_scope(db, data, file_hash)
            check_hash(db, file_hash)
            previous = None
            if substituir_id:
                old = replacement_target(db, data, substituir_id)
                previous = (jsonable_encoder(detail(old)), old.evidencia_bucket, old.evidencia_path)
                db.delete(old)
                db.flush()
            check_sections(db, data)
            boletim = make_boletim(data, filename, file_hash, bucket, path)
            if previous:
                snapshot, boletim.evidencia_bucket, boletim.evidencia_path = previous
                boletim.historico_manual = [
                    {"substituido_em": datetime.now(timezone.utc).isoformat(), "boletim": snapshot}
                ]
            db.add(boletim)
            db.flush()
            boletim_id = boletim.id
            storage.upload(bucket, path, pdf)
            uploaded = True
        return {"id": boletim_id, "detail": "Boletim salvo com sucesso."}
    except (StorageError, SQLAlchemyError) as exc:
        # Reset even a Session left in 'committed' state by a lost commit response.
        db.close()
        if uploaded:
            existing_id = _recover_upload(db, data, file_hash, bucket, path, storage)
            if existing_id:
                return {"id": existing_id, "detail": "Boletim salvo com sucesso."}
        if isinstance(exc, IntegrityError):
            raise HTTPException(
                409, "Arquivo ou seção já cadastrado por outra importação."
            ) from exc
        if isinstance(exc, StorageError):
            raise HTTPException(
                502, "Falha no storage. Nenhum boletim foi gravado. Tente novamente."
            ) from exc
        logger.exception("Falha ao confirmar boletim")
        raise HTTPException(
            503,
            "Falha no banco. Consulte a listagem antes de tentar novamente.",
            headers={"Retry-After": "2"},
        ) from exc
