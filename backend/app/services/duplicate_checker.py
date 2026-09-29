import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Boletim, BoletimSecao
from app.core.locks import lock_keys
from app.schemas.boletim import BoletimDados


def check_hash(db: Session, file_hash: str):
    if db.scalar(select(Boletim.id).where(Boletim.arquivo_hash == file_hash)):
        raise HTTPException(409, "Este arquivo já foi importado anteriormente.")


def scope(data: BoletimDados):
    return dict(
        eleicao_data=data.eleicao.data,
        eleicao_turno=data.eleicao.turno,
        municipio_codigo=str(int(data.municipio.codigo)),
        zona=str(int(data.zona)),
    )


def lock_scope(db: Session, data: BoletimDados, file_hash: str):
    identity = [
        data.eleicao.data.isoformat(),
        data.eleicao.turno,
        str(int(data.municipio.codigo)),
        str(int(data.zona)),
    ]
    # Unrelated sections can upload together; shared main/aggregated sections cannot.
    lock_keys(
        db,
        [
            f"hash:{file_hash}",
            *[
                "section:" + json.dumps([*identity, str(int(number))], separators=(",", ":"))
                for number in [data.secao, *data.secoes_agregadas]
            ],
        ],
    )


def check_sections(db: Session, data: BoletimDados):
    statement = (
        select(BoletimSecao.numero_secao)
        .filter_by(**scope(data))
        .where(
            BoletimSecao.secao_chave.in_(
                [str(int(s)) for s in [data.secao, *data.secoes_agregadas]]
            )
        )
    )
    if db.scalar(statement):
        raise HTTPException(
            409,
            "Uma das seções representadas por este boletim já está cadastrada, como principal ou agregada.",
        )
