import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Boletim, BoletimSecao, Resultado, CandidatoVoto
from app.services.boletim_service import make_boletim
from app.services.bu_parser import parse_bu_text
from app.services.pdf_reader import extract_text_from_pdf


def preview(client, pdf):
    response = client.post(
        "/api/boletins/preview", files={"file": ("bu.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 200, response.text
    return response.json()


def counts(engine):
    with Session(engine) as db:
        return [
            db.scalar(select(func.count()).select_from(m))
            for m in [Boletim, BoletimSecao, Resultado, CandidatoVoto]
        ]


def test_end_to_end(client, pdf, engine, storage):
    p = preview(client, pdf)
    receipt_url = f"/api/boletins/por-hash/{p['hash']}"
    assert client.get(receipt_url).json() is None
    assert p["status"] == "OK"
    assert counts(engine) == [0, 0, 0, 0]
    assert not storage.objects
    saved = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert saved.status_code == 201, saved.text
    assert counts(engine) == [1, 5, 1, 11]
    assert list(storage.objects.values()) == [pdf]
    receipt = client.get(receipt_url)
    assert receipt.json() == {"id": saved.json()["id"]}
    assert receipt.headers["Cache-Control"] == "no-store"
    listing = client.get("/api/boletins").json()
    assert listing[0]["secao"] == "0483"
    result = client.get("/api/boletins/" + saved.json()["id"]).json()
    assert result["dados"]["cargos"][0]["votos_nominais"] == 175
    assert len(result["secoes"]) == 5
    assert result["storage_path"].startswith("2018/turno-1/30848/0001/0483/")
    assert client.get(f"/api/boletins/{result['id']}/pdf").status_code == 200
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": p["preview_token"]}
        ).status_code
        == 409
    )
    duplicate = client.post(
        "/api/boletins/preview", files={"file": ("bu.pdf", pdf, "application/pdf")}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Este arquivo já foi importado anteriormente."


@pytest.mark.parametrize(
    "principal,aggregated",
    [("0483", []), ("0999", ["0483"]), ("0486", []), ("0999", ["0941"]), ("483", [])],
)
def test_overlapping_sections(client, pdf, engine, principal, aggregated):
    data = parse_bu_text(extract_text_from_pdf(pdf))
    data.secao = principal
    data.secoes_agregadas = aggregated
    data.quantidade_secoes_agregadas = len(aggregated)
    with Session(engine) as db, db.begin():
        db.add(make_boletim(data, "different.pdf", "a" * 64, "boletins", "other.pdf"))
    p = preview(client, pdf)
    result = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert result.status_code == 409
    assert counts(engine)[0] == 1


def test_storage_failure_rolls_back(client, pdf, engine, storage):
    p = preview(client, pdf)
    storage.fail = True
    result = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert result.status_code == 502
    assert counts(engine) == [0, 0, 0, 0]
    storage.fail = False
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": p["preview_token"]}
        ).status_code
        == 201
    )


def test_database_commit_failure_compensates_storage(client, pdf, engine, storage):
    p = preview(client, pdf)

    def fail_commit(session):
        raise OperationalError("simulated commit failure", {}, Exception())

    event.listen(Session, "before_commit", fail_commit)
    try:
        result = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert result.status_code == 503
    assert counts(engine) == [0, 0, 0, 0]
    assert not storage.objects


def test_concurrent_confirmation(client, pdf, engine, storage):
    p = preview(client, pdf)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    client.post(
                        "/api/boletins/confirmar", json={"preview_token": p["preview_token"]}
                    ).status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [201, 409]
    assert counts(engine) == [1, 5, 1, 11]
    assert len(storage.objects) == 1


def test_concurrent_different_files_same_section(client, pdf, engine, storage):
    previews = [
        preview(client, file)["preview_token"] for file in [pdf, pdf + b"\n% different file\n"]
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda token: (
                    client.post(
                        "/api/boletins/confirmar", json={"preview_token": token}
                    ).status_code
                ),
                previews,
            )
        )
    assert sorted(responses) == [201, 409]
    assert counts(engine) == [1, 5, 1, 11]
    assert len(storage.objects) == 1


def test_tampered_expired_and_extra_fields(client, pdf):
    p = preview(client, pdf)
    token = p["preview_token"]
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": token[:50] + "!" + token[51:]}
        ).status_code
        == 410
    )
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": token, "votos": 999}
        ).status_code
        == 422
    )
    f = Fernet(get_settings().preview_secret_key)
    expired = f.encrypt_at_time(f.decrypt(token), int(time.time()) - 3601).decode()
    assert (
        client.post("/api/boletins/confirmar", json={"preview_token": expired}).status_code == 410
    )


@pytest.mark.parametrize(
    "filename,mime,content,status",
    [
        ("x.txt", "application/pdf", b"x", 415),
        ("x.pdf", "text/plain", b"x", 415),
        ("x.pdf", "application/pdf", b"not pdf", 422),
        ("x.pdf", "application/pdf", b"x" * (11 * 1024 * 1024), 413),
    ],
)
def test_invalid_upload(client, filename, mime, content, status):
    assert (
        client.post("/api/boletins/preview", files={"file": (filename, content, mime)}).status_code
        == status
    )


def test_not_found(client):
    assert client.get("/api/boletins/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/boletins/por-hash/invalid").status_code == 422


def test_inconsistent_pdf_cannot_be_saved(client, pdf, engine):
    import pymupdf

    text = extract_text_from_pdf(pdf).replace("0175", "0174")
    with pymupdf.open() as doc:
        page = doc.new_page(width=800, height=2000)
        page.insert_text((20, 20), text, fontsize=10)
        bad_pdf = doc.tobytes()
    p = preview(client, bad_pdf)
    assert p["status"] == "INCONSISTENTE"
    assert len(p["problemas"]) == 2
    result = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert result.status_code == 422
    assert counts(engine) == [0, 0, 0, 0]
