import pytest

from app.core.config import get_settings


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/api/boletins",
        "/api/acompanhamento",
        "/api/acompanhamento/votos-secao?zona=0013&secao=0010",
        "/api/telao/config",
        "/api/telao/candidatos-disponiveis?cargo=SENADOR",
        "/api/divulgacao",
    ],
)
def test_read_routes_work_without_credentials(client, path):
    assert "Authorization" not in client.headers
    response = client.get(path)
    assert response.status_code == 200
    assert "WWW-Authenticate" not in response.headers
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/logout"),
    ],
)
def test_login_endpoints_are_removed(client, method, path):
    assert client.request(method, path).status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert not any(path.startswith("/api/auth") for path in paths)


def test_import_read_pdf_and_duplicate_detection_without_login(client, pdf, storage):
    preview = client.post(
        "/api/boletins/preview", files={"file": ("test.pdf", pdf, "application/pdf")}
    )
    assert preview.status_code == 200
    token = preview.json()["preview_token"]
    confirmed = client.post("/api/boletins/confirmar", json={"preview_token": token})
    assert confirmed.status_code == 201
    bulletin_id = confirmed.json()["id"]
    assert client.get(f"/api/boletins/{bulletin_id}").status_code == 200
    assert client.get(f"/api/boletins/{bulletin_id}/pdf").status_code == 200
    assert len(client.get("/api/boletins").json()) == 1
    assert len(storage.objects) == 1
    assert client.post("/api/boletins/confirmar", json={"preview_token": token}).status_code == 409


def test_screen_configuration_still_validates_input_and_version_without_login(client):
    original = client.get("/api/telao/config").json()
    assert client.put("/api/telao/config", json={}).status_code == 422
    body = {
        "versao": original["versao"],
        "cards_por_pagina": 6,
        "tempo_rotacao_segundos": 10,
        "ativo": True,
        "candidatos": [],
    }
    saved = client.put("/api/telao/config", json=body)
    assert saved.status_code == 200
    assert saved.json()["versao"] == original["versao"] + 1
    assert client.put("/api/telao/config", json=body).status_code == 409


def test_cors_keeps_explicit_origin_without_login_headers(client):
    response = client.options(
        "/api/telao/config",
        headers={
            "Origin": get_settings().frontend_url,
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == get_settings().frontend_url
    response = client.options(
        "/api/telao/config",
        headers={
            "Origin": "https://other.example.test",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
