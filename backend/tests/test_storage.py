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


@pytest.mark.parametrize("status", [400, 404])
def test_photo_bucket_is_created_private_only_when_missing(status):
    calls = []

    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, json={"code": "NoSuchBucket"})
        if request.method == "POST":
            import json

            assert json.loads(request.content) == {
                "id": "candidatos",
                "name": "candidatos",
                "public": False,
                "allowed_mime_types": ["image/webp"],
                "file_size_limit": 2097152,
            }
            return httpx.Response(200, json={"name": "candidatos"})
        return httpx.Response(200, json={"id": "candidatos", "public": False})

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        storage = StorageService(client)
        storage.settings = storage.settings.model_copy(
            update={
                "supabase_url": "https://project.supabase.co",
                "supabase_service_role_key": "test",
            }
        )
        storage.ensure_photo_bucket("candidatos")
    assert [request.method for request in calls] == ["GET", "POST", "GET"]


def test_existing_photo_bucket_is_not_modified_and_auth_failures_do_not_create_it():
    responses = iter(
        [
            httpx.Response(200, json={"public": False}),
            httpx.Response(200, json={"public": True}),
            httpx.Response(400, json={"code": "AccessDenied"}),
        ]
    )

    def handle(request):
        assert request.method == "GET"
        return next(responses)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        storage = StorageService(client)
        storage.settings = storage.settings.model_copy(
            update={
                "supabase_url": "https://project.supabase.co",
                "supabase_service_role_key": "test",
            }
        )
        storage.ensure_photo_bucket("candidatos")
        with pytest.raises(StorageError, match="privado"):
            storage.ensure_photo_bucket("candidatos")
        with pytest.raises(StorageError) as error:
            storage.ensure_photo_bucket("candidatos")
        assert error.value.code == "AccessDenied"


def test_simultaneous_photo_bucket_creation_rechecks_privacy():
    responses = iter(
        [
            httpx.Response(400, json={"code": "NoSuchBucket"}),
            httpx.Response(400, json={"code": "BucketAlreadyExists"}),
            httpx.Response(200, json={"public": False}),
        ]
    )
    with httpx.Client(transport=httpx.MockTransport(lambda request: next(responses))) as client:
        storage = StorageService(client)
        storage.settings = storage.settings.model_copy(
            update={
                "supabase_url": "https://project.supabase.co",
                "supabase_service_role_key": "test",
            }
        )
        storage.ensure_photo_bucket("candidatos")


def test_photo_mime_and_download_do_not_change_pdf_defaults():
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, content=b"image")

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        storage = StorageService(client)
        storage.settings = storage.settings.model_copy(
            update={
                "supabase_url": "https://project.supabase.co",
                "supabase_service_role_key": "test",
            }
        )
        storage.upload("candidatos", "a.webp", b"image", content_type="image/webp")
        assert calls[-1].headers["content-type"] == "image/webp"
        assert storage.download("candidatos", "a.webp") == b"image"
        assert calls[-1].url.path.endswith("/object/authenticated/candidatos/a.webp")
        storage.upload("boletins", "a.pdf", b"pdf")
        assert calls[-1].headers["content-type"] == "application/pdf"
