import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

os.environ["PREVIEW_SECRET_KEY"] = Fernet.generate_key().decode()
os.environ["TELAO_REALTIME_ENABLED"] = "false"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://apuracao:apuracao@localhost:55432/apuracao"
)

from app.core.database import get_db
from app.core.config import get_settings
from app.main import app
from app.services.storage_service import get_storage, StorageError


@pytest.fixture(scope="session")
def pdf():
    return (Path(__file__).resolve().parents[2] / "Xangai_(ZZ)_-_0001_-_0483.pdf").read_bytes()


@pytest.fixture(scope="session")
def engine():
    url = os.environ["DATABASE_URL"]
    admin = create_engine(url)
    schema = "test_" + uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    settings = get_settings()
    engine = create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout_seconds,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    import app.core.database as database

    original = database.get_engine
    database.get_engine = lambda: engine
    try:
        command.upgrade(Config("alembic.ini"), "head")
        yield engine
    finally:
        database.get_engine = original
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


class FakeStorage:
    def __init__(self):
        self.objects = {}
        self.fail = False

    def upload(self, bucket, path, content):
        if self.fail:
            raise StorageError("simulated")
        assert (bucket, path) not in self.objects
        self.objects[bucket, path] = content

    def delete(self, bucket, path):
        self.objects.pop((bucket, path), None)

    def signed_url(self, bucket, path):
        return "https://example.test/signed.pdf"


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def client(engine, storage, monkeypatch):
    from tests.auth_fixture import ADMIN_ID, TOKEN, fake_auth_request

    monkeypatch.setattr(get_settings(), "admin_user_ids", ADMIN_ID)
    monkeypatch.setattr("app.core.auth.auth_request", fake_auth_request)
    monkeypatch.setattr("app.api.auth.auth_request", fake_auth_request)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE boletins, secoes_esperadas, telao_config CASCADE"))

    def db_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_storage] = lambda: storage
    with TestClient(
        app, client=("127.0.0.1", 50000), headers={"Authorization": f"Bearer {TOKEN}"}
    ) as client:
        yield client
    app.dependency_overrides.clear()
