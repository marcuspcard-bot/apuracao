from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.bu_parser import parse_bu_text
from app.services.duplicate_checker import lock_scope
from app.services.file_hash import calculate_sha256
from app.services.pdf_reader import extract_text_from_pdf
from app.services.storage_service import StorageError
from tests.acompanhamento_fixture import bacabal_text
from tests.multicargo_fixture import render_pdf
from tests.test_api import counts, preview


def confirm(client, token):
    return client.post("/api/boletins/confirmar", json={"preview_token": token})


def test_five_independent_imports_in_same_zone_and_live_overview(
    client, pdf, engine, storage, monkeypatch
):
    source = extract_text_from_pdf(pdf)
    documents = [
        render_pdf(bacabal_text(source, section, aggregates))
        for section, aggregates in [
            ("0001", ["0002", "0003"]),
            ("0004", []),
            ("0005", []),
            ("0006", []),
            ("0007", []),
        ]
    ]
    with ThreadPoolExecutor(max_workers=5) as pool:
        previews = list(pool.map(lambda doc: preview(client, doc), documents))
    assert all(p["status"] == "OK" for p in previews)
    assert counts(engine) == [0, 0, 0, 0]

    uploads_ready = Barrier(6, timeout=15)
    release_uploads = Event()
    upload = storage.upload

    def blocked_upload(*args):
        uploads_ready.wait()
        assert release_uploads.wait(15), "Test did not release uploads"
        upload(*args)

    monkeypatch.setattr(storage, "upload", blocked_upload)
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(confirm, client, p["preview_token"]) for p in previews]
        try:
            # All five must reach Storage together: no zone-wide serialization.
            uploads_ready.wait()
            assert client.get("/health").status_code == 200
            pending = client.get("/api/acompanhamento").json()
            assert pending["boletins"] == pending["secoes_apuradas"] == 0
            assert pending["cargos"] == []
            assert client.get("/api/boletins").json() == []
            assert client.get("/api/divulgacao").json()["boletins_recebidos"] == 0
            assert client.get(f"/api/boletins/por-hash/{previews[0]['hash']}").json() is None
            overloaded = confirm(client, previews[0]["preview_token"])
            assert overloaded.status_code == 503
            assert overloaded.headers["Retry-After"] == "2"
            assert "importações em processamento" in overloaded.json()["detail"]
        finally:
            release_uploads.set()
        responses = [future.result(timeout=30) for future in futures]

    assert [r.status_code for r in responses] == [201] * 5, [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 5
    assert counts(engine) == [5, 7, 15, 20]
    assert len(storage.objects) == 5
    result = client.get("/api/acompanhamento").json()
    assert result["boletins"] == 5
    assert result["secoes_apuradas"] == 7
    cargos = {c["nome"]: c for c in result["cargos"]}
    assert cargos["PRESIDENTE"]["candidatos"][0]["votos"] == 150
    assert cargos["PRESIDENTE"]["candidatos"][1]["votos"] == 0
    assert cargos["GOVERNADOR"]["candidatos"][0]["votos"] == 35
    assert cargos["DEPUTADO FEDERAL"]["candidatos"][0]["votos"] == 50
    assert engine.pool.checkedout() == 0


def test_one_failed_upload_does_not_rollback_the_other_four(
    client, pdf, engine, storage, monkeypatch
):
    source = extract_text_from_pdf(pdf)
    previews = [preview(client, render_pdf(bacabal_text(source, f"{i + 1:04}"))) for i in range(5)]
    ready = Barrier(5, timeout=15)
    upload = storage.upload

    def sometimes_fails(bucket, path, content):
        ready.wait()
        if "/0003/" in path:
            raise StorageError("one simulated connection failure")
        upload(bucket, path, content)

    monkeypatch.setattr(storage, "upload", sometimes_fails)
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(lambda p: confirm(client, p["preview_token"]), previews))
    assert [r.status_code for r in responses] == [201, 201, 502, 201, 201]
    assert counts(engine) == [4, 4, 12, 16]
    assert len(storage.objects) == 4
    assert client.get(f"/api/boletins/por-hash/{previews[2]['hash']}").json() is None
    for index in (0, 1, 3, 4):
        assert client.get(f"/api/boletins/por-hash/{previews[index]['hash']}").json() == {
            "id": responses[index].json()["id"]
        }
    monkeypatch.setattr(storage, "upload", upload)
    assert confirm(client, previews[2]["preview_token"]).status_code == 201
    assert counts(engine) == [5, 5, 15, 20]
    assert len(storage.objects) == 5
    assert engine.pool.checkedout() == 0


@pytest.mark.parametrize("conflict", ["same_file", "same_section", "shared_aggregate"])
def test_five_conflicting_imports_save_exactly_once(client, pdf, engine, storage, conflict):
    source = extract_text_from_pdf(pdf)
    if conflict == "same_file":
        tokens = [preview(client, pdf)["preview_token"]] * 5
    elif conflict == "same_section":
        tokens = [
            preview(client, pdf + f"\n% variant {i}\n".encode())["preview_token"] for i in range(5)
        ]
    else:
        tokens = [
            preview(
                client, render_pdf(bacabal_text(source, f"{i + 1:04}", ["0099" if i % 2 else "99"]))
            )["preview_token"]
            for i in range(5)
        ]
    start = Barrier(5, timeout=15)

    def run(token):
        start.wait()
        return confirm(client, token)

    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(run, tokens))
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409, 409]
    assert counts(engine)[0] == 1
    assert len(storage.objects) == 1
    if conflict == "shared_aggregate":
        overview = client.get("/api/acompanhamento").json()
        assert overview["secoes_apuradas"] == 2
        assert (
            next(c for c in overview["cargos"] if c["nome"] == "PRESIDENTE")["candidatos"][0][
                "votos"
            ]
            == 30
        )


def test_lock_wait_is_bounded_and_retry_succeeds(client, pdf, engine, storage, monkeypatch):
    token = preview(client, pdf)["preview_token"]
    data = parse_bu_text(extract_text_from_pdf(pdf))
    monkeypatch.setattr(get_settings(), "db_lock_timeout_ms", 100)
    with Session(engine) as blocker, blocker.begin():
        lock_scope(blocker, data, calculate_sha256(pdf))
        response = confirm(client, token)
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "2"
        assert counts(engine) == [0, 0, 0, 0]
        assert not storage.objects
    assert confirm(client, token).status_code == 201


def test_lost_commit_response_recovers_without_deleting_saved_pdf(client, pdf, engine, storage):
    token = preview(client, pdf)["preview_token"]
    failed = False

    def lose_response(session):
        nonlocal failed
        if not failed:
            failed = True
            raise OperationalError("simulated lost commit response", {}, Exception())

    event.listen(Session, "after_commit", lose_response)
    try:
        response = confirm(client, token)
    finally:
        event.remove(Session, "after_commit", lose_response)
    assert response.status_code == 201, response.text
    assert counts(engine) == [1, 5, 1, 11]
    assert list(storage.objects.values()) == [pdf]
    assert client.get("/api/boletins/" + response.json()["id"]).status_code == 200
