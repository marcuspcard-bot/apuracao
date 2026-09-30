"""Isolated browser-test server. Storage is an in-memory test double, never production."""

import os
from contextlib import asynccontextmanager
from uuid import uuid4
from pathlib import Path

import uvicorn
import pymupdf
from alembic import command
from alembic.config import Config
from fastapi import Response
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core import database
from app.core.config import get_settings
from app.main import app
from app.services.storage_service import get_storage
from app.services.pdf_reader import extract_text_from_pdf
from app.services.pdf_processing import shutdown_pdf_pool
from app.services.telao_realtime import ScreenEvents
from tests.multicargo_fixture import document_text, render_pdf, OFFICES, office_text
from tests.test_sections import standalone_text
from tests.acompanhamento_fixture import bacabal_text

schema = "e2e_" + uuid4().hex
url = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://apuracao:apuracao@localhost:55432/apuracao"
)
admin = create_engine(url)
engine = create_engine(
    url,
    pool_size=get_settings().db_pool_size,
    max_overflow=get_settings().db_max_overflow,
    pool_timeout=get_settings().db_pool_timeout_seconds,
    connect_args={"options": f"-csearch_path={schema}"},
)


class BrowserStorage:
    objects = {}

    def upload(self, bucket, path, content):
        self.objects[bucket, path] = content

    def delete(self, bucket, path):
        self.objects.pop((bucket, path), None)

    def signed_url(self, bucket, path):
        return f"http://127.0.0.1:8001/test-pdf/{bucket}/{path}"


storage = BrowserStorage()


def db_override():
    with Session(engine) as db:
        yield db


@asynccontextmanager
async def lifespan(app):
    root = Path(__file__).resolve().parents[2]
    artifacts = root / ".artifacts"
    artifacts.mkdir(exist_ok=True)
    source = extract_text_from_pdf((root / "Xangai_(ZZ)_-_0001_-_0483.pdf").read_bytes())
    for section, aggregated in [("0001", ["0002", "0003"]), ("0004", [])]:
        (artifacts / f"bacabal-sintetico-{section}.pdf").write_bytes(
            render_pdf(bacabal_text(source, section, aggregated))
        )
    for section in ("0009", "0010"):
        (artifacts / f"bacabal-telao-{section}.pdf").write_bytes(
            render_pdf(bacabal_text(source, section))
        )
    for section in ("0301", "0302", "0303", "0304", "0305", "0310", "0320", "0321"):
        aggregates = ["0351", "0352"] if section == "0301" else []
        (artifacts / f"simultaneo-{section}.pdf").write_bytes(
            render_pdf(bacabal_text(source, section, aggregates))
        )
    (artifacts / "bacabal-outra-data.pdf").write_bytes(
        render_pdf(
            bacabal_text(source, "0002", ["0165", "0167", "0168", "0169"]).replace(
                "04/10/2026", "02/10/2026"
            )
        )
    )
    (artifacts / "sem-agregadas.pdf").write_bytes(
        render_pdf(standalone_text(source, omit_count=True))
    )
    (artifacts / "agregadas-inconsistentes.pdf").write_bytes(
        render_pdf(source.replace("0486 0941 0488 1123", "0486 0941 0488"))
    )
    multi = document_text(source)
    (artifacts / "multicargos.pdf").write_bytes(render_pdf(multi))
    (artifacts / "total-ausente.pdf").write_bytes(
        render_pdf(multi.replace("Total Apurado 0077", ""))
    )
    senate = office_text(OFFICES[3])
    seats = document_text(source, [OFFICES[3]], section="0888").replace(
        senate,
        senate.replace(" SENADOR ", " SENADOR - 1ª VAGA ")
        + senate.replace(" SENADOR ", " SENADOR - 2ª VAGA "),
    )
    (artifacts / "vagas-senador.pdf").write_bytes(render_pdf(seats))
    with pymupdf.open() as doc:
        page = doc.new_page(width=800, height=2000)
        page.insert_text((20, 20), source.replace("0175", "0174"), fontsize=10)
        doc.save(artifacts / "inconsistente.pdf")
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    original = database.get_engine
    database.get_engine = lambda: engine
    try:
        command.upgrade(Config("alembic.ini"), "head")
        app.dependency_overrides[database.get_db] = db_override
        app.dependency_overrides[get_storage] = lambda: storage
        app.state.screen_events = ScreenEvents()
        os.environ["TELAO_REALTIME_ENABLED"] = "false"
        from app.core.config import get_settings

        get_settings.cache_clear()
        await app.state.screen_events.start()
        yield
    finally:
        await app.state.screen_events.stop()
        shutdown_pdf_pool()
        database.get_engine = original
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@app.get("/test-pdf/{bucket}/{path:path}")
def original_pdf(bucket: str, path: str):
    return Response(storage.objects[bucket, path], media_type="application/pdf")


app.router.lifespan_context = lifespan

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
