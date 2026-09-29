import httpx
import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient
from app.api.auth import router
from app.core import auth
from app.core.config import get_settings
from tests.auth_fixture import ADMIN_ID, TOKEN, fake_auth_request


@pytest.fixture
def auth_client(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_user_ids", ADMIN_ID)
    monkeypatch.setattr(auth, "auth_request", fake_auth_request)
    monkeypatch.setattr("app.api.auth.auth_request", fake_auth_request)
    app = FastAPI()
    app.include_router(router)

    @app.get("/private", dependencies=[Depends(auth.require_admin)])
    def private():
        return {"ok": True}

    return TestClient(app)


def test_login_logout_and_restricted_access(auth_client):
    assert auth_client.get("/private").status_code == 401
    assert (
        auth_client.get("/private", headers={"Authorization": "Bearer forged"}).status_code == 401
    )
    bad = auth_client.post(
        "/api/auth/login", json={"email": "admin@example.test", "password": "wrong"}
    )
    assert bad.status_code == 401
    result = auth_client.post(
        "/api/auth/login", json={"email": "admin@example.test", "password": "test-password"}
    )
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert set(result.json()) == {"access_token", "expires_in", "user"}
    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert auth_client.get("/api/auth/me", headers=headers).json()["id"] == ADMIN_ID
    assert auth_client.post("/api/auth/logout", headers=headers).status_code == 204


def test_non_admin_and_missing_configuration_fail_closed(auth_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_user_ids", "another-user")
    assert (
        auth_client.get("/private", headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 403
    )
    assert (
        auth_client.post(
            "/api/auth/login", json={"email": "admin@example.test", "password": "test-password"}
        ).status_code
        == 403
    )
    monkeypatch.setattr(get_settings(), "admin_user_ids", "")
    with pytest.raises(HTTPException) as exc:
        auth.authorize_user({"id": ADMIN_ID, "user_metadata": {"admin": True}})
    assert exc.value.status_code == 403


@pytest.mark.parametrize("status,expected", [(401, 401), (403, 401), (429, 429), (500, 503)])
def test_provider_errors_are_sanitized(monkeypatch, status, expected):
    monkeypatch.setattr(get_settings(), "admin_user_ids", ADMIN_ID)
    monkeypatch.setattr(get_settings(), "supabase_url", "https://auth.example.test")
    monkeypatch.setattr(get_settings(), "supabase_service_role_key", "server-secret")

    def request(self, method, url, **kwargs):
        assert kwargs["headers"]["Authorization"] == "Bearer user-token"
        return httpx.Response(status, json={"message": "private-provider-details"})

    monkeypatch.setattr(httpx.Client, "request", request)
    with pytest.raises(HTTPException) as exc:
        auth.auth_request("GET", "user", token="user-token")
    assert exc.value.status_code == expected
    assert "private-provider-details" not in exc.value.detail


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/boletins"),
        ("POST", "/api/boletins/preview"),
        ("POST", "/api/boletins/confirmar"),
        ("GET", "/api/acompanhamento"),
        ("POST", "/api/acompanhamento/secoes/confirmar"),
        ("GET", "/api/telao/config"),
    ],
)
def test_actual_routes_reject_anonymous_before_database(method, path):
    from app.main import app

    client = TestClient(app)
    assert client.request(method, path).status_code == 401
    assert client.get("/health").status_code == 200
