from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, joinedload

from app.core.locks import lock_keys
from app.models import Boletim, CandidatoVoto, Resultado, TelaoCandidato, TelaoConfig
from app.schemas.telao import TelaoSave
from app.services.acompanhamento import ELEICAO_DATA, MUNICIPIO_CODIGO, TURNO
from app.services.offices import RECOGNIZED_OFFICES

ZONA = "0013"


def bulletin_scope():
    return (
        func.ltrim(Boletim.municipio_codigo, "0") == MUNICIPIO_CODIGO.lstrip("0"),
        func.ltrim(Boletim.zona, "0") == ZONA.lstrip("0"),
        Boletim.eleicao_data == ELEICAO_DATA,
        Boletim.eleicao_turno == TURNO,
    )


def load_config(db: Session):
    # Read the configuration and selections in a single snapshot.
    return (
        db.execute(
            select(TelaoConfig)
            .where(TelaoConfig.id == 1)
            .options(joinedload(TelaoConfig.candidatos))
        )
        .unique()
        .scalar_one_or_none()
    )


def config_response(config: TelaoConfig | None):
    return {
        "municipio": "BACABAL",
        "municipio_codigo": MUNICIPIO_CODIGO,
        "uf": "MA",
        "zona": ZONA,
        "eleicao_data": ELEICAO_DATA,
        "eleicao_turno": TURNO,
        "cards_por_pagina": config.cards_por_pagina if config else 6,
        "tempo_rotacao_segundos": config.tempo_rotacao_segundos if config else 10,
        "ativo": config.ativo if config else True,
        "versao": config.versao if config else 0,
        "updated_at": config.updated_at if config else None,
        "cargos": list(RECOGNIZED_OFFICES),
        "candidatos": [
            {
                "id": c.id,
                "candidato_id": c.candidato_id,
                "cargo": c.cargo,
                "numero": c.numero_candidato,
                "nome": c.nome_candidato,
                "ordem": c.ordem,
                "ativo": c.ativo,
            }
            for c in sorted(config.candidatos, key=lambda c: c.ordem)
        ]
        if config
        else [],
    }


def candidate_sources():
    return (
        select(
            CandidatoVoto.id.label("candidato_id"),
            Resultado.cargo,
            CandidatoVoto.numero_candidato.label("numero"),
            CandidatoVoto.nome_candidato.label("nome"),
        )
        .join(Resultado, Resultado.id == CandidatoVoto.resultado_id)
        .join(Boletim, Boletim.id == Resultado.boletim_id)
        .where(*bulletin_scope())
        .distinct(Resultado.cargo, CandidatoVoto.numero_candidato)
        .order_by(
            Resultado.cargo,
            CandidatoVoto.numero_candidato,
            CandidatoVoto.nome_candidato,
            CandidatoVoto.id,
        )
    )


def available_candidates(db: Session, cargo: str, query: str, offset: int, limit: int):
    statement = candidate_sources().where(Resultado.cargo == cargo)
    if query.strip():
        statement = statement.where(
            CandidatoVoto.nome_candidato.icontains(query.strip(), autoescape=True)
            | CandidatoVoto.numero_candidato.contains(query.strip(), autoescape=True)
        )
    rows = db.execute(statement.offset(offset).limit(limit + 1)).mappings().all()
    return {"candidatos": [dict(row) for row in rows[:limit]], "tem_mais": len(rows) > limit}


def save_config(db: Session, body: TelaoSave):
    with db.begin():
        lock_keys(db, ["telao-config:1"])
        config = load_config(db)
        version = config.versao if config else 0
        if body.versao != version:
            raise HTTPException(
                409, "A configuração mudou em outra janela. Recarregue antes de salvar."
            )
        existing = {(c.cargo, c.numero_candidato): c for c in config.candidatos} if config else {}
        keys = [(c.cargo, c.numero) for c in body.candidatos]
        sources = (
            {
                (row.cargo, row.numero): row
                for row in db.execute(
                    candidate_sources().where(
                        tuple_(Resultado.cargo, CandidatoVoto.numero_candidato).in_(keys)
                    )
                )
            }
            if keys
            else {}
        )
        if any(key not in existing and key not in sources for key in keys):
            raise HTTPException(
                422,
                "Selecione candidatos existentes nos boletins de Bacabal, zona 0013, desta eleição.",
            )
        if config is None:
            config = TelaoConfig(
                id=1,
                municipio_codigo=MUNICIPIO_CODIGO,
                municipio_nome="BACABAL",
                uf="MA",
                zona=ZONA,
                eleicao_data=ELEICAO_DATA,
                eleicao_turno=TURNO,
            )
            db.add(config)
        now = datetime.now(timezone.utc)
        config.cards_por_pagina = body.cards_por_pagina
        config.tempo_rotacao_segundos = body.tempo_rotacao_segundos
        config.ativo = body.ativo
        config.versao = version + 1
        config.updated_at = now
        selected = []
        for order, item in enumerate(body.candidatos, start=1):
            key = (item.cargo, item.numero)
            entry = existing.get(key)
            if entry is None:
                source = sources[key]
                entry = TelaoCandidato(
                    candidato_id=source.candidato_id,
                    cargo=item.cargo,
                    numero_candidato=item.numero,
                    nome_candidato=source.nome,
                )
            entry.ordem, entry.ativo, entry.updated_at = order, item.ativo, now
            selected.append(entry)
        config.candidatos = selected
        db.flush()
        response = config_response(config)
    return response
