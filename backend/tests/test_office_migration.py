from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text, Table, MetaData

from app.core import database
from app.services.boletim_service import make_boletim
from app.services.bu_parser import parse_bu_text
from app.services.pdf_reader import extract_text_from_pdf


def test_upgrade_preserves_old_rows_and_defaults_legend(engine, pdf, monkeypatch):
    schema = "migration_" + uuid4().hex
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = create_engine(engine.url, connect_args={"options": f"-csearch_path={schema}"})
    monkeypatch.setattr(database, "get_engine", lambda: isolated)
    config = Config("alembic.ini")
    try:
        command.upgrade(config, "97a4a50a18c8")
        data = parse_bu_text(extract_text_from_pdf(pdf))
        boletim = make_boletim(data, "existing.pdf", "e" * 64, "boletins", "existing.pdf")
        boletim.resultados = []
        # Insert using the historical schema, not today's ORM columns.
        boletim_id = uuid4()
        metadata = MetaData()
        old_boletins = Table("boletins", metadata, autoload_with=isolated)
        old_sections = Table("boletim_secoes", metadata, autoload_with=isolated)
        with isolated.begin() as conn:
            conn.execute(
                old_boletins.insert().values(
                    id=boletim_id,
                    **{
                        c.name: getattr(boletim, c.name)
                        for c in old_boletins.columns
                        if c.name not in ("id", "created_at")
                    },
                )
            )
            for section in boletim.secoes:
                conn.execute(
                    old_sections.insert().values(
                        id=uuid4(),
                        boletim_id=boletim_id,
                        **{
                            c.name: getattr(section, c.name)
                            for c in old_sections.columns
                            if c.name not in ("id", "boletim_id")
                        },
                    )
                )
        result_id, candidate_id = uuid4(), uuid4()
        with isolated.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO resultados (id, boletim_id, cargo, votos_nominais, brancos, nulos, total_apurado) VALUES (:id, :bu, 'PRESIDENTE', 175, 5, 15, 195)"
                ),
                {"id": result_id, "bu": boletim_id},
            )
            conn.execute(
                text(
                    "INSERT INTO votos_candidatos (id, resultado_id, numero_candidato, nome_candidato, votos) VALUES (:id, :result, '12', 'CIRO GOMES', 16)"
                ),
                {"id": candidate_id, "result": result_id},
            )
        command.upgrade(config, "head")
        with isolated.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT id, votos_nominais, votos_legenda, brancos, nulos, total_apurado, vagas FROM resultados"
                )
            ).one()
            assert tuple(row) == (result_id, 175, 0, 5, 15, 195, [])
            assert conn.execute(
                text("SELECT id, numero_candidato, votos, vaga FROM votos_candidatos")
            ).one() == (candidate_id, "12", 16, "")
            assert conn.scalar(text("SELECT count(*) FROM boletins")) == 1
            assert conn.execute(
                text("SELECT origem, historico_manual, evidencia_path FROM boletins")
            ).one() == ("PDF", [], None)
            assert conn.scalar(text("SELECT count(*) FROM boletim_secoes")) == 5
            assert conn.scalar(text("SELECT count(*) FROM secoes_esperadas")) == 0
            assert (
                conn.scalar(
                    text(
                        "SELECT relrowsecurity FROM pg_class WHERE oid = 'secoes_esperadas'::regclass"
                    )
                )
                is True
            )
        command.check(config)
    finally:
        isolated.dispose()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
