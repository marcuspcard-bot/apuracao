from datetime import datetime, timezone

from sqlalchemy import case, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.models import Boletim, BoletimSecao, CandidatoVoto, Resultado, SecaoEsperada
from app.services.acompanhamento import ELEICAO_DATA, MUNICIPIO_CODIGO, TURNO
from app.services.telao_service import ZONA, bulletin_scope, config_response, load_config


def _bulletins(db: Session):
    # Only confirmed imports exist here. Previews, errors and duplicates are not persisted.
    return db.execute(select(Boletim.id, Boletim.created_at).where(*bulletin_scope())).all()


def _totals(db: Session, bulletin_ids, candidates):
    if not bulletin_ids or not candidates:
        return {}
    keys = [(c["cargo"], c["numero"]) for c in candidates]
    votes = (
        select(
            Resultado.cargo,
            CandidatoVoto.numero_candidato.label("numero"),
            CandidatoVoto.votos,
            CandidatoVoto.vaga,
            func.max(case((CandidatoVoto.vaga == "", 1), else_=0))
            .over(partition_by=(CandidatoVoto.resultado_id, CandidatoVoto.numero_candidato))
            .label("has_overall"),
        )
        .join(Resultado, Resultado.id == CandidatoVoto.resultado_id)
        .where(
            Resultado.boletim_id.in_(bulletin_ids),
            tuple_(Resultado.cargo, CandidatoVoto.numero_candidato).in_(keys),
        )
        .subquery()
    )
    # Senate seat breakdowns are not added again when an overall candidate row exists.
    effective = case((or_(votes.c.vaga == "", votes.c.has_overall == 0), votes.c.votos), else_=0)
    rows = db.execute(
        select(votes.c.cargo, votes.c.numero, func.sum(effective).label("votos")).group_by(
            votes.c.cargo, votes.c.numero
        )
    )
    return {(row.cargo, row.numero): row.votos for row in rows}


def divulgacao(db: Session):
    config = config_response(load_config(db))
    candidates = [c for c in config["candidatos"] if c["ativo"]] if config["ativo"] else []
    bulletins = _bulletins(db)
    ids = [b.id for b in bulletins]
    totals = _totals(db, ids, candidates)
    # Coverage has its own query; it never joins candidate votes.
    represented = (
        db.scalar(
            select(func.count(func.distinct(BoletimSecao.secao_chave))).where(
                BoletimSecao.boletim_id.in_(ids)
            )
        )
        if ids
        else 0
    )
    expected = db.scalar(
        select(func.count())
        .select_from(SecaoEsperada)
        .where(
            SecaoEsperada.municipio_codigo == str(int(MUNICIPIO_CODIGO)),
            SecaoEsperada.zona_chave == str(int(ZONA)),
            SecaoEsperada.eleicao_data == ELEICAO_DATA,
            SecaoEsperada.eleicao_turno == TURNO,
        )
    )
    return {
        "municipio": "BACABAL",
        "uf": "MA",
        "zona": ZONA,
        "eleicao_data": ELEICAO_DATA,
        "eleicao_turno": TURNO,
        "boletins_recebidos": len(ids),
        "secoes_representadas": represented,
        "total_secoes_esperadas": expected or None,
        "ultima_atualizacao": datetime.now(timezone.utc),
        "ultima_importacao": max((b.created_at for b in bulletins), default=None),
        "cards_por_pagina": config["cards_por_pagina"],
        "tempo_rotacao_segundos": config["tempo_rotacao_segundos"],
        "ativo": config["ativo"],
        "versao": config["versao"],
        "candidatos": [
            {key: c[key] for key in ("id", "ordem", "cargo", "numero", "nome")}
            | {"votos": totals.get((c["cargo"], c["numero"]), 0)}
            for c in candidates
        ],
    }
