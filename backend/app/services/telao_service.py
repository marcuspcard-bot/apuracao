from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, joinedload

from app.core.locks import lock_keys
from app.models import Boletim, CandidatoVoto, Resultado, TelaoCandidato, TelaoConfig
from app.schemas.telao import TelaoSave
from app.services.acompanhamento import ELEICAO_DATA, MUNICIPIO_CODIGO, TURNO
from app.services.candidate_identity import candidate_key, candidate_key_sql
from app.services.offices import RECOGNIZED_OFFICES
from app.services.candidate_photos import (
    discard_photos,
    discard_uncommitted_photos,
    photo_url,
    prepare_photo,
    store_photo,
)
from app.services.storage_service import StorageError

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


def unique_selections(config):
    entries = {}
    for entry in sorted(config.candidatos, key=lambda c: c.ordem) if config else []:
        entries.setdefault((entry.cargo, candidate_key(entry.numero_candidato)), entry)
    return entries


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
                "foto_url": photo_url(c),
            }
            for c in unique_selections(config).values()
        ]
        if config
        else [],
    }


def candidate_sources():
    number_key = candidate_key_sql(CandidatoVoto.numero_candidato)
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
        .distinct(Resultado.cargo, number_key)
        .order_by(
            Resultado.cargo,
            number_key,
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
            | candidate_key_sql(CandidatoVoto.numero_candidato).contains(
                candidate_key(query.strip()) if query.strip().isdecimal() else query.strip(),
                autoescape=True,
            )
        )
    rows = db.execute(statement.offset(offset).limit(limit + 1)).mappings().all()
    return {"candidatos": [dict(row) for row in rows[:limit]], "tem_mais": len(rows) > limit}


def save_config(db: Session, body: TelaoSave, storage):
    uploaded, obsolete = [], []
    try:
        result = _save_config(db, body, storage, uploaded, obsolete)
    except Exception as exc:
        discard_uncommitted_photos(db, storage, uploaded)
        if isinstance(exc, StorageError):
            raise HTTPException(
                502, "Não foi possível salvar a foto no Storage. Tente novamente."
            ) from exc
        raise
    discard_photos(storage, obsolete)
    return result


def _save_config(db: Session, body: TelaoSave, storage, uploaded, obsolete):
    with db.begin():
        lock_keys(db, ["telao-config:1"])
        config = load_config(db)
        version = config.versao if config else 0
        if body.versao != version:
            raise HTTPException(
                409, "A configuração mudou em outra janela. Recarregue antes de salvar."
            )
        existing = unique_selections(config)
        keys = [(c.cargo, candidate_key(c.numero)) for c in body.candidatos]
        sources = (
            {
                (row.cargo, candidate_key(row.numero)): row
                for row in db.execute(
                    candidate_sources().where(
                        tuple_(
                            Resultado.cargo, candidate_key_sql(CandidatoVoto.numero_candidato)
                        ).in_(keys)
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
            key = (item.cargo, candidate_key(item.numero))
            entry = existing.get(key)
            if entry is None:
                source = sources[key]
                entry = TelaoCandidato(
                    id=uuid4(),
                    candidato_id=source.candidato_id,
                    cargo=item.cargo,
                    numero_candidato=item.numero,
                    nome_candidato=source.nome,
                )
            if "foto" in item.model_fields_set:
                if entry.foto_path:
                    obsolete.append((entry.foto_bucket, entry.foto_path))
                if item.foto is None:
                    entry.foto_bucket = entry.foto_path = None
                else:
                    store_photo(storage, entry, prepare_photo(item.foto), uploaded)
            entry.ordem, entry.ativo, entry.updated_at = order, item.ativo, now
            selected.append(entry)
        obsolete.extend(
            (entry.foto_bucket, entry.foto_path)
            for entry in config.candidatos
            if entry not in selected and entry.foto_path
        )
        config.candidatos = selected
        db.flush()
        response = config_response(config)
    return response
