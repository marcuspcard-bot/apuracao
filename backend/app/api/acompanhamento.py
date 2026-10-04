from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

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


@router.get("/relatorio")
def get_report(
    response: Response,
    eleicao_data: date = Query(ELEICAO_DATA, alias="data"),
    db: Session = Depends(get_db),
):
    from app.services.relatorios import report_data

    response.headers["Cache-Control"] = "no-store"
    return report_data(db, eleicao_data)


@router.get("/relatorio.csv")
def export_report(
    cargo: str = Query(min_length=1, max_length=100),
    candidatos: list[str] = Query(min_length=1, max_length=200),
    eleicao_data: date = Query(ELEICAO_DATA, alias="data"),
    db: Session = Depends(get_db),
):
    from app.services.relatorios import csv_report, report_data

    if any(not n.isascii() or not n.isdigit() or len(n) > 20 for n in candidatos):
        raise HTTPException(422, "Número de candidato inválido.")
    try:
        content = csv_report(report_data(db, eleicao_data), cargo, candidatos)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="relatorio-{eleicao_data}.csv"',
            "Cache-Control": "no-store",
        },
    )


class ReportCandidate(BaseModel):
    cargo: str = Field(min_length=1, max_length=100)
    numero: str = Field(pattern=r"^[0-9]{1,20}$")


class ReportSelection(BaseModel):
    data: date = ELEICAO_DATA
    candidatos: list[ReportCandidate] = Field(min_length=1, max_length=200)


@router.post("/relatorio.csv")
def export_selected_report(body: ReportSelection, db: Session = Depends(get_db)):
    from app.services.relatorios import csv_report_selected, report_data

    try:
        content = csv_report_selected(
            report_data(db, body.data), [c.model_dump() for c in body.candidatos]
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="relatorio-{body.data}.csv"',
            "Cache-Control": "no-store",
        },
    )
