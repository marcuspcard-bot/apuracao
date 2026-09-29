from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from threading import Barrier, BoundedSemaphore
from time import sleep
from unittest.mock import Mock
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Request

from app.core import database
from app.core.database import get_engine
from app.core.config import get_settings
from app.services import importacao_service, pdf_processing
from app.main import lifespan
from app.services.storage_service import get_storage
from tests.test_api import preview


def test_storage_client_is_shared_and_closed_at_shutdown():
    async def run():
        app = SimpleNamespace(state=SimpleNamespace())
        request = Request({"type": "http", "app": app})
        async with lifespan(app):
            storage = get_storage(request)
            assert all(get_storage(request) is storage for _ in range(5))
            assert not storage.client.is_closed
        assert storage.client.is_closed

    asyncio.run(run())


def test_preview_and_confirmation_parse_without_holding_connection(
    client, pdf, engine, monkeypatch
):
    parse = importacao_service.parse_pdf
    calls = []

    def check_connections(content):
        calls.append(engine.pool.checkedout())
        return parse(content)

    monkeypatch.setattr(importacao_service, "parse_pdf", check_connections)
    token = preview(client, pdf)["preview_token"]
    assert client.post("/api/boletins/confirmar", json={"preview_token": token}).status_code == 201
    assert calls == [0, 0]


def test_signing_url_does_not_hold_connection(client, pdf, engine, storage, monkeypatch):
    token = preview(client, pdf)["preview_token"]
    saved = client.post("/api/boletins/confirmar", json={"preview_token": token}).json()

    def signed_url(bucket, path):
        assert engine.pool.checkedout() == 0
        return "https://example.test/signed.pdf"

    monkeypatch.setattr(storage, "signed_url", signed_url)
    assert client.get(f"/api/boletins/{saved['id']}/pdf").status_code == 200


def test_running_pdf_timeout_keeps_slot_until_worker_finishes(monkeypatch):
    future = Future()
    future.set_running_or_notify_cancel()
    slots = BoundedSemaphore(1)
    pool = Mock()
    pool.submit.return_value = future
    monkeypatch.setattr(pdf_processing, "_get_pool", lambda: (pool, slots))
    monkeypatch.setattr(get_settings(), "pdf_timeout_seconds", 0.01)
    with pytest.raises(pdf_processing.PdfProcessingError, match="tempo limite"):
        pdf_processing.read_pdf_text(b"pdf")
    with pytest.raises(pdf_processing.PdfProcessingError, match="ocupada"):
        pdf_processing.read_pdf_text(b"pdf")
    assert pool.submit.call_count == 1
    assert not future.cancelled()
    future.set_result("text")
    assert pdf_processing.read_pdf_text(b"pdf") == "text"


def test_queued_pdf_timeout_cancels_and_releases_slot(monkeypatch):
    future = Future()
    slots = BoundedSemaphore(1)
    pool = Mock()
    pool.submit.return_value = future
    monkeypatch.setattr(pdf_processing, "_get_pool", lambda: (pool, slots))
    monkeypatch.setattr(get_settings(), "pdf_timeout_seconds", 0.01)
    with pytest.raises(pdf_processing.PdfProcessingError, match="tempo limite"):
        pdf_processing.read_pdf_text(b"pdf")
    assert future.cancelled()
    assert slots.acquire(blocking=False)


@pytest.mark.parametrize("during_submit", [True, False])
def test_failed_pdf_pool_is_discarded_and_slot_released(monkeypatch, during_submit):
    future = Future()
    future.set_exception(BrokenProcessPool("worker exited"))
    slots = BoundedSemaphore(1)
    pool, shutdown = Mock(), Mock()
    if during_submit:
        pool.submit.side_effect = BrokenProcessPool("worker exited")
    else:
        pool.submit.return_value = future
    monkeypatch.setattr(pdf_processing, "_get_pool", lambda: (pool, slots))
    monkeypatch.setattr(pdf_processing, "shutdown_pdf_pool", shutdown)
    with pytest.raises(pdf_processing.PdfProcessingError):
        pdf_processing.read_pdf_text(b"pdf")
    shutdown.assert_called_once_with(pool)
    assert slots.acquire(blocking=False)


def test_busy_pdf_processing_returns_retryable_error(client, pdf, monkeypatch):
    def busy(content):
        raise pdf_processing.PdfProcessingError("A leitura de PDFs esta ocupada.")

    monkeypatch.setattr(importacao_service, "read_pdf_text", busy)
    response = client.post(
        "/api/boletins/preview", files={"file": ("bu.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"


def test_database_pool_configuration_and_single_initialization(monkeypatch):
    def initialize(*args, **kwargs):
        sleep(0.02)
        return object()

    create_engine = Mock(side_effect=initialize)
    monkeypatch.setattr(database, "create_engine", create_engine)
    monkeypatch.setattr(get_settings(), "database_url", "postgresql://user:password@localhost/test")
    database._create_engine.cache_clear()
    start = Barrier(5, timeout=10)

    def get_pool(_):
        start.wait()
        return get_engine()

    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            engines = list(pool.map(get_pool, range(5)))
        assert all(engine is engines[0] for engine in engines)
        create_engine.assert_called_once_with(
            "postgresql+psycopg://user:password@localhost/test",
            pool_pre_ping=True,
            hide_parameters=True,
            pool_size=5,
            max_overflow=5,
            pool_timeout=10,
            connect_args={"connect_timeout": 10},
        )
    finally:
        database._create_engine.cache_clear()
