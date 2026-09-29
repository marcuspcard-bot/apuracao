from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.acompanhamento import ELEICAO_DATA, SECTION_SCOPE, overview, section_votes
from app.schemas.secoes_esperadas import ConfirmarCadastro
from app.services.secoes_esperadas import (
    load_sections,
    list_version,
    parse_sections_csv,
    save_sections,
)

router = APIRouter(prefix="/api/acompanhamento", tags=["Acompanhamento"])


@router.get("")
def get_overview(
    response: Response,
    eleicao_data: date = Query(ELEICAO_DATA, alias="data"),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return overview(db, eleicao_data)


@router.get("/votos-secao")
def get_section_votes(
    response: Response,
    zona: str = Query(pattern=r"^[0-9]{1,20}$"),
    secao: str = Query(pattern=r"^[0-9]{1,20}$"),
    eleicao_data: date = Query(ELEICAO_DATA, alias="data"),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return section_votes(db, zona, secao, eleicao_data)


@router.post("/secoes/preview")
def preview_sections(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(415, "Envie a lista em um arquivo .csv.")
    content = file.file.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise HTTPException(413, "A lista excede o limite de 1 MB.")
    try:
        parsed = parse_sections_csv(content)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    current = load_sections(db, SECTION_SCOPE)
    return {
        **parsed.model_dump(),
        "versao_lista": list_version(current),
        "substitui_lista": bool(current),
        "total_secoes": sum(1 + len(g.secoes_agregadas) for g in parsed.grupos),
    }


@router.post("/secoes/confirmar")
def confirm_sections(body: ConfirmarCadastro, db: Session = Depends(get_db)):
    save_sections(db, SECTION_SCOPE, body)
    return {"detail": "Lista de seções salva."}
