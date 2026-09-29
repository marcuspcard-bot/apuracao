import httpx
import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

from app.services.storage_service import StorageService, StorageError, create_storage_client


def test_supabase_requests(monkeypatch):
    client = Mock(spec=httpx.Client)
    storage = StorageService(client)
    storage.settings = storage.settings.model_copy(
        update={
            "supabase_url": "https://project.supabase.co",
            "supabase_service_role_key": "test-secret",
        }
    )
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        assert kwargs["headers"]["Authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            json={"signedURL": "/object/sign/boletins/a.pdf?token=test"},
            request=httpx.Request(method, url),
        )

    client.request.side_effect = request
    storage.upload("boletins", "a.pdf", b"%PDF-test")
    assert calls[-1][2]["content"] == b"%PDF-test"
    assert calls[-1][2]["headers"]["x-upsert"] == "false"
    assert (
        storage.signed_url("boletins", "a.pdf")
        == "https://project.supabase.co/storage/v1/object/sign/boletins/a.pdf?token=test"
    )
    assert calls[-1][2]["json"] == {"expiresIn": 60}
    storage.delete("boletins", "a.pdf")
    assert calls[-1][2]["json"] == {"prefixes": ["a.pdf"]}


def test_recovers_ambiguous_upload(monkeypatch):
    storage = StorageService(Mock(spec=httpx.Client))

    def request(method, path, **kwargs):
        if method == "POST":
            raise StorageError("upload response lost")
        return httpx.Response(200, content=b"original")

    monkeypatch.setattr(storage, "request", request)
    storage.upload("boletins", "a.pdf", b"original")
    with pytest.raises(StorageError):
        storage.upload("boletins", "a.pdf", b"different")


def test_shared_storage_client_accepts_five_uploads():
    ready = Barrier(5, timeout=10)

    def handle(request):
        ready.wait()
        assert request.headers["Authorization"] == "Bearer test-secret"
        assert request.headers["x-upsert"] == "false"
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        storage = StorageService(client)
        storage.settings = storage.settings.model_copy(
            update={
                "supabase_url": "https://project.supabase.co",
                "supabase_service_role_key": "test-secret",
            }
        )
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda i: storage.upload("boletins", f"{i}.pdf", b"pdf"), range(5)))
        assert not client.is_closed
    assert client.is_closed


def test_storage_pool_and_timeouts_are_bounded(monkeypatch):
    factory = Mock()
    monkeypatch.setattr(httpx, "Client", factory)
    assert create_storage_client() is factory.return_value
    options = factory.call_args.kwargs
    assert options["limits"].max_connections == 10
    assert options["limits"].max_keepalive_connections == 10
    assert options["timeout"].connect == 10
    assert options["timeout"].read == options["timeout"].write == 45
    assert options["timeout"].pool == 5
