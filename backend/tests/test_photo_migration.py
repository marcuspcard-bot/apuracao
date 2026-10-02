from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core import database


def test_photo_migration_preserves_existing_screen_configuration(engine, monkeypatch):
    schema = "migration_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = create_engine(engine.url, connect_args={"options": f"-csearch_path={schema}"})
    monkeypatch.setattr(database, "get_engine", lambda: isolated)
    config = Config("alembic.ini")
    candidate_id = uuid4()
    try:
        command.upgrade(config, "d13e840a6c27")
        with isolated.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO telao_config
                (id, municipio_codigo, municipio_nome, uf, zona, eleicao_data, eleicao_turno,
                 cards_por_pagina, tempo_rotacao_segundos, ativo, versao)
                VALUES (1, '07234', 'BACABAL', 'MA', '0013', '2026-10-04', 1, 5, 15, true, 7)
            """)
            )
            connection.execute(
                text("""
                INSERT INTO telao_candidatos
                (id, config_id, cargo, numero_candidato, nome_candidato, ordem, ativo)
                VALUES (:id, 1, 'DEPUTADO FEDERAL', '0123', 'CANDIDATO TESTE', 1, true)
            """),
                {"id": candidate_id},
            )
        command.upgrade(config, "head")
        with isolated.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT id, nome_candidato, numero_candidato, ordem, ativo, foto_bucket, foto_path "
                    "FROM telao_candidatos"
                )
            ).one() == (candidate_id, "CANDIDATO TESTE", "0123", 1, True, None, None)
            assert connection.execute(
                text("SELECT versao, cards_por_pagina, tempo_rotacao_segundos FROM telao_config")
            ).one() == (7, 5, 15)
        command.check(config)
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
