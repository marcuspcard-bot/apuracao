from datetime import date, datetime, timezone

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Boletim, BoletimSecao, CandidatoVoto, Resultado
from app.services.candidate_identity import candidate_key, candidate_key_sql
from app.services.secoes_esperadas import load_sections, section_status

# TSE: mun-e000619-cm.json (municipality identity), CDE 2026 (election date).
MUNICIPIO_CODIGO = "07234"
ELEICAO_DATA = date(2026, 10, 4)
TURNO = 1
SECTION_SCOPE = {
    "municipio_codigo": str(int(MUNICIPIO_CODIGO)),
    "eleicao_data": ELEICAO_DATA,
    "eleicao_turno": TURNO,
}


def _scope_filters():
    return (
        func.ltrim(Boletim.municipio_codigo, "0") == MUNICIPIO_CODIGO.lstrip("0"),
        Boletim.eleicao_turno == TURNO,
    )


def _load_bulletins(
    db: Session,
    election_date: date = ELEICAO_DATA,
    *,
    zone: str | None = None,
    section: str | None = None,
):
    statement = select(
        Boletim.id, Boletim.zona, Boletim.secao, Boletim.created_at, Boletim.origem
    ).where(*_scope_filters(), Boletim.eleicao_data == election_date)
    if zone is not None and section is not None:
        statement = statement.where(
            Boletim.id.in_(
                select(BoletimSecao.boletim_id).where(
                    BoletimSecao.zona == str(int(zone)),
                    BoletimSecao.secao_chave == str(int(section)),
                )
            )
        )
    return db.execute(statement.order_by(Boletim.zona, Boletim.secao, Boletim.id)).all()


def _available_dates(db: Session, selected_date: date, selected_count: int):
    rows = db.execute(
        select(Boletim.eleicao_data, func.count().label("boletins"))
        .where(*_scope_filters())
        .group_by(Boletim.eleicao_data)
    )
    counts = {row.eleicao_data: row.boletins for row in rows}
    counts.setdefault(ELEICAO_DATA, 0)
    # Match the frozen bulletin set used for the selected date's votes and sections.
    counts[selected_date] = selected_count
    days = [ELEICAO_DATA, *sorted(set(counts) - {ELEICAO_DATA}, reverse=True)]
    return [{"data": day, "boletins": counts[day]} for day in days]


def _load_covered_sections(db: Session, bulletins):
    if not bulletins:
        return []
    rows = db.execute(
        select(BoletimSecao.boletim_id, BoletimSecao.numero_secao, BoletimSecao.tipo).where(
            BoletimSecao.boletim_id.in_(bulletins)
        )
    )
    return sorted(
        [
            {
                "zona": bulletins[s.boletim_id].zona,
                "secao": s.numero_secao,
                "tipo": s.tipo,
                "secao_principal": bulletins[s.boletim_id].secao,
                "boletim_id": str(s.boletim_id),
                "parcial": bulletins[s.boletim_id].origem == "MANUAL",
            }
            for s in rows
        ],
        key=lambda s: (int(s["zona"]), int(s["secao"])),
    )


def _summarize_candidates(db: Session, bulletin_ids):
    if not bulletin_ids:
        return []
    counts = db.execute(
        select(Resultado.cargo, func.count().label("boletins"))
        .where(Resultado.boletim_id.in_(bulletin_ids))
        .group_by(Resultado.cargo)
    )
    offices = {r.cargo: {"boletins": r.boletins, "candidatos": {}} for r in counts}
    votes = (
        select(
            Resultado.cargo,
            CandidatoVoto.numero_candidato.label("numero"),
            CandidatoVoto.nome_candidato.label("nome"),
            CandidatoVoto.vaga,
            CandidatoVoto.votos,
            func.max(case((CandidatoVoto.vaga == "", 1), else_=0))
            .over(
                partition_by=(
                    CandidatoVoto.resultado_id,
                    candidate_key_sql(CandidatoVoto.numero_candidato),
                )
            )
            .label("has_overall"),
        )
        .join(Resultado, Resultado.id == CandidatoVoto.resultado_id)
        .where(Resultado.boletim_id.in_(bulletin_ids))
        .subquery()
    )
    # Count a bulletin once, excluding seat rows when an overall row already includes them.
    effective_votes = case(
        (or_(votes.c.vaga == "", votes.c.has_overall == 0), votes.c.votos), else_=0
    )
    totals = db.execute(
        select(
            votes.c.cargo,
            votes.c.numero,
            votes.c.nome,
            votes.c.vaga,
            func.sum(votes.c.votos).label("votos_vaga"),
            func.sum(effective_votes).label("votos"),
        ).group_by(votes.c.cargo, votes.c.numero, votes.c.nome, votes.c.vaga)
    )
    for row in totals:
        entry = offices[row.cargo]["candidatos"].setdefault(
            candidate_key(row.numero),
            {
                "numero": row.numero,
                "nomes": set(),
                "votos": 0,
                "vagas": {},
            },
        )
        entry["numero"] = min(entry["numero"], row.numero)
        entry["nomes"].add(row.nome)
        entry["votos"] += row.votos
        entry["vagas"][row.vaga] = entry["vagas"].get(row.vaga, 0) + row.votos_vaga
    cargos = []
    for name, office in sorted(offices.items()):
        candidates = []
        for entry in office["candidatos"].values():
            names = sorted(entry["nomes"])
            candidates.append(
                {
                    "numero": entry["numero"],
                    "nome": names[0],
                    "nomes": names,
                    "votos": entry["votos"],
                    "vagas": [
                        {"identificacao": k or None, "votos": v}
                        for k, v in sorted(entry["vagas"].items())
                    ],
                }
            )
        cargos.append(
            {
                "nome": name,
                "boletins": office["boletins"],
                "candidatos": sorted(candidates, key=lambda c: (-c["votos"], c["numero"])),
            }
        )
    return cargos


def section_votes(db: Session, zone: str, section: str, election_date: date = ELEICAO_DATA):
    bulletins = {b.id: b for b in _load_bulletins(db, election_date, zone=zone, section=section)}
    return {
        "boletins": len(bulletins),
        "secoes": _load_covered_sections(db, bulletins),
        "cargos": _summarize_candidates(db, list(bulletins)),
    }


def overview(db: Session, election_date: date = ELEICAO_DATA):
    # Freeze the bulletin set so a concurrent import cannot appear in only some totals.
    bulletins = {b.id: b for b in _load_bulletins(db, election_date)}
    sections = _load_covered_sections(db, bulletins)
    cargos = _summarize_candidates(db, list(bulletins))
    return {
        "municipio": {"nome": "Bacabal", "uf": "MA", "codigo": MUNICIPIO_CODIGO},
        "eleicao": {"ano": election_date.year, "turno": TURNO, "data": election_date},
        "eleicao_configurada": {"ano": ELEICAO_DATA.year, "turno": TURNO, "data": ELEICAO_DATA},
        "datas_disponiveis": _available_dates(db, election_date, len(bulletins)),
        "consultado_em": datetime.now(timezone.utc),
        "ultima_importacao": max((b.created_at for b in bulletins.values()), default=None),
        "boletins": len(bulletins),
        "secoes_apuradas": sum(not s["parcial"] for s in sections),
        "boletins_manuais": sum(b.origem == "MANUAL" for b in bulletins.values()),
        **section_status(
            load_sections(db, {**SECTION_SCOPE, "eleicao_data": election_date}), sections
        ),
        "secoes": sections,
        "cargos": cargos,
    }
