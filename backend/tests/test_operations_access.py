import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, Mock

from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.api.health import router as health_router
from app.core import access, monitoring
from app.core.config import Settings
from app.services import health


KEY = "a" * 43


def settings(**kwargs):
    return Settings(
        _env_file=None,
        database_url="postgresql://local/test",
        preview_secret_key=Fernet.generate_key().decode(),
        operator_access_mode=kwargs.pop("operator_access_mode", "proxy"),
        operator_proxy_key=kwargs.pop("operator_proxy_key", KEY),
        **kwargs,
    )


@pytest.fixture
def protected_client(monkeypatch):
    monkeypatch.setattr(access, "get_settings", lambda: settings())
    app = FastAPI()
    app.include_router(health_router)
    app.dependency_overrides[health.database_ready] = lambda: True

    @app.api_route("/api/boletins", methods=["GET", "POST"])
    @app.put("/api/telao/config")
    @app.get("/api/divulgacao")
    @app.get("/api/divulgacao/eventos")
    def endpoint(request: Request):
        return {"headers": dict(request.headers)}

    app.add_middleware(access.OperatorAccessMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://frontend.example"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(monitoring.RequestLoggingMiddleware)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "path", ["/health", "/ready", "/api/divulgacao", "/api/divulgacao/eventos"]
)
def test_public_read_only_routes_remain_public(protected_client, path):
    response = protected_client.get(path)
    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) == 32


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/boletins"),
        ("POST", "/api/boletins"),
        ("PUT", "/api/telao/config"),
        ("GET", "/openapi.json"),
        ("GET", "/docs"),
        ("POST", "/api/divulgacao"),
        ("GET", "/api/divulgacao-privada"),
        ("GET", "/api/divulgacao/anything"),
    ],
)
def test_operator_routes_deny_direct_access(protected_client, method, path):
    response = protected_client.request(
        method, path, headers={"X-Forwarded-For": "127.0.0.1", "Origin": "https://frontend.example"}
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert "WWW-Authenticate" not in response.headers


def test_gateway_key_is_checked_and_not_forwarded_to_application(protected_client):
    assert (
        protected_client.get("/api/boletins", headers={"X-Operator-Proxy-Key": "wrong"}).status_code
        == 403
    )
    assert (
        protected_client.get(
            "/api/boletins", headers=[("X-Operator-Proxy-Key", KEY), ("X-Operator-Proxy-Key", KEY)]
        ).status_code
        == 403
    )
    response = protected_client.post("/api/boletins", headers={"X-Operator-Proxy-Key": KEY})
    assert response.status_code == 200
    assert "x-operator-proxy-key" not in response.json()["headers"]


def test_preflight_does_not_authorize_the_actual_request(protected_client):
    headers = {
        "Origin": "https://frontend.example",
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "Content-Type",
    }
    assert protected_client.options("/api/telao/config", headers=headers).status_code == 200
    assert (
        protected_client.put("/api/telao/config", headers={"Origin": headers["Origin"]}).status_code
        == 403
    )
    headers["Access-Control-Request-Headers"] = "X-Operator-Proxy-Key"
    assert protected_client.options("/api/telao/config", headers=headers).status_code == 400


@pytest.mark.parametrize("value", ["", "short", "a" * 42, "a" * 129, "x" * 43 + "\n"])
def test_proxy_mode_refuses_missing_or_unsafe_key(value):
    with pytest.raises(ValidationError):
        settings(operator_proxy_key=value)


def test_request_logs_do_not_contain_secrets(protected_client, monkeypatch):
    log = Mock()
    monkeypatch.setattr(monitoring.logger, "log", log)
    response = protected_client.post(
        "/api/boletins?token=query-secret",
        json={"preview_token": "body-secret"},
        headers={"X-Operator-Proxy-Key": KEY, "X-Request-ID": "untrusted-id"},
    )
    entry = json.loads(log.call_args.args[1])
    assert entry["route"] == "/api/boletins"
    assert entry["request_id"] == response.headers["x-request-id"]
    assert entry["status"] == 200
    for secret in (KEY, "query-secret", "body-secret", "untrusted-id"):
        assert secret not in log.call_args.args[1]


def test_readiness_503_is_generic_and_liveness_stays_up(protected_client):
    protected_client.app.dependency_overrides[health.database_ready] = lambda: False
    response = protected_client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert protected_client.get("/health").status_code == 200


def test_readiness_caches_results_and_recovers(monkeypatch):
    engine = MagicMock()
    engine.connect.side_effect = SQLAlchemyError("do-not-expose")
    probe = health.DatabaseProbe(lambda: engine, ttl=10)
    clock = [0]
    monkeypatch.setattr(health, "monotonic", lambda: clock[0])
    assert probe.check() is False
    assert probe.check() is False
    assert engine.connect.call_count == 1
    clock[0] = 11
    engine.connect.side_effect = None
    engine.connect.return_value.__enter__.return_value.scalar.return_value = 1
    assert probe.check() is True


def test_readiness_uses_one_probe_for_concurrent_requests():
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value.scalar.return_value = 1
    probe = health.DatabaseProbe(lambda: engine)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert all(pool.map(lambda _: probe.check(), range(16)))
    assert engine.connect.call_count == 1


def test_readiness_with_actual_test_database(engine):
    assert health.DatabaseProbe(lambda: engine).check() is True
