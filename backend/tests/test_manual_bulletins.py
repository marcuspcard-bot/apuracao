from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Boletim, CandidatoVoto
from app.services.bu_parser import parse_bu_text
from app.services.pdf_reader import extract_text_from_pdf


def payload(pdf):
    data = parse_bu_text(extract_text_from_pdf(pdf))
    candidate = data.cargos[0].candidatos[0]
    return {
        "eleicao": data.eleicao.model_dump(mode="json"),
        "municipio": data.municipio.model_dump(),
        "zona": data.zona,
        "secao": data.secao,
        "secoes_agregadas": data.secoes_agregadas,
        "candidatos": [
            dict(
                cargo=data.cargos[0].nome,
                numero=candidate.numero,
                nome=candidate.nome,
                votos=candidate.votos + 5,
            )
        ],
    }


def save(client, body):
    response = client.post("/api/boletins/manual/confirmar", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def preview(client, pdf, target=None):
    response = client.post(
        "/api/boletins/preview",
        params={"substituir_id": target} if target else {},
        files={"file": ("bu.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_partial_zero_unknown_and_duplicates(client, pdf, engine):
    body = payload(pdf)
    body["candidatos"][0]["votos"] = 0
    target = save(client, body)
    details = client.get(f"/api/boletins/{target}").json()
    assert details["origem"] == "MANUAL"
    assert details["dados"]["eleitores"]["comparecimento"] is None
    assert details["cargos"][0]["candidatos"][0]["votos"] == 0
    assert details["cargos"][0]["votos_legenda"] is None
    assert details["cargos"][0]["total_apurado"] is None
    assert client.get(f"/api/boletins/{target}/pdf").status_code == 404
    body["secao"] = str(int(body["secao"]))
    assert client.post("/api/boletins/manual/confirmar", json=body).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(CandidatoVoto)) == 1


@pytest.mark.parametrize(
    "change", ["negative", "missing", "candidate_duplicate", "section_duplicate", "office"]
)
def test_manual_validation(client, pdf, change):
    body = payload(pdf)
    if change == "negative":
        body["candidatos"][0]["votos"] = -1
    if change == "missing":
        del body["candidatos"][0]["votos"]
    if change == "candidate_duplicate":
        body["candidatos"] *= 2
    if change == "section_duplicate":
        body["secoes_agregadas"].append(body["secao"])
    if change == "office":
        body["candidatos"][0]["cargo"] = "INVALIDO"
    assert client.post("/api/boletins/manual/confirmar", json=body).status_code == 422


def test_replace_does_not_add_votes_and_keeps_history(client, pdf, engine):
    body = payload(pdf)
    target = save(client, body)
    p = preview(client, pdf, target)
    assert p["substituicao"]["id"] == target
    result = client.post(
        "/api/boletins/confirmar",
        json={"preview_token": p["preview_token"], "substituir_id": target},
    )
    assert result.status_code == 201, result.text
    details = client.get("/api/boletins/" + result.json()["id"]).json()
    assert details["origem"] == "PDF"
    assert (
        details["historico_manual"][0]["boletim"]["cargos"][0]["candidatos"][0]["votos"]
        == body["candidatos"][0]["votos"]
    )
    data = parse_bu_text(extract_text_from_pdf(pdf))
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Boletim)) == 1
        assert db.scalar(select(func.sum(CandidatoVoto.votos))) == sum(
            c.votos for c in data.cargos[0].candidatos
        )
    assert client.get(f"/api/boletins/{target}").status_code == 404
    assert (
        client.post(
            "/api/boletins/confirmar",
            json={"preview_token": p["preview_token"], "substituir_id": target},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("change", ["section", "date", "aggregates", "candidate"])
def test_wrong_pdf_cannot_replace(client, pdf, change):
    body = payload(pdf)
    if change == "section":
        body["secao"] = "9999"
    if change == "date":
        body["eleicao"]["data"] = "2026-10-04"
    if change == "aggregates":
        body["secoes_agregadas"] = []
    if change == "candidate":
        body["candidatos"][0]["numero"] = "99999"
    target = save(client, body)
    p = preview(client, pdf)
    response = client.post(
        "/api/boletins/confirmar",
        json={"preview_token": p["preview_token"], "substituir_id": target},
    )
    assert response.status_code == 422
    assert client.get(f"/api/boletins/{target}").json()["origem"] == "MANUAL"


def test_storage_failure_preserves_manual(client, pdf, storage):
    target = save(client, payload(pdf))
    p = preview(client, pdf, target)
    storage.fail = True
    response = client.post(
        "/api/boletins/confirmar",
        json={"preview_token": p["preview_token"], "substituir_id": target},
    )
    assert response.status_code == 502
    assert client.get(f"/api/boletins/{target}").json()["origem"] == "MANUAL"


def test_commit_failure_preserves_manual(client, pdf, storage):
    target = save(client, payload(pdf))
    p = preview(client, pdf, target)

    def fail_commit(session):
        raise OperationalError("simulated", {}, Exception())

    event.listen(Session, "before_commit", fail_commit)
    try:
        response = client.post(
            "/api/boletins/confirmar",
            json={"preview_token": p["preview_token"], "substituir_id": target},
        )
    finally:
        event.remove(Session, "before_commit", fail_commit)
    assert response.status_code == 503
    assert client.get(f"/api/boletins/{target}").json()["origem"] == "MANUAL"
    assert not storage.objects


def test_concurrent_replacement_only_once(client, pdf, engine):
    target = save(client, payload(pdf))
    p = preview(client, pdf, target)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: (
                    client.post(
                        "/api/boletins/confirmar",
                        json={"preview_token": p["preview_token"], "substituir_id": target},
                    ).status_code
                ),
                range(2),
            )
        )
    assert sorted(results) == [201, 409]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Boletim)) == 1


def test_photos_pdf_retained_after_replacement(client, pdf, storage):
    out = BytesIO()
    Image.new("RGB", (200, 300), "white").save(out, format="JPEG")
    photos = client.post(
        "/api/boletins/fotos/preview", files=[("files", ("bu.jpg", out.getvalue(), "image/jpeg"))]
    )
    assert photos.status_code == 200, photos.text
    body = payload(pdf)
    body["foto_token"] = photos.json()["foto_token"]
    target = save(client, body)
    assert client.get(f"/api/boletins/{target}/fotos").status_code == 200
    assert next(iter(storage.objects.values())).startswith(b"%PDF")
    p = preview(client, pdf, target)
    replaced = client.post(
        "/api/boletins/confirmar",
        json={"preview_token": p["preview_token"], "substituir_id": target},
    ).json()["id"]
    assert client.get(f"/api/boletins/{replaced}").json()["tem_foto"]
    assert client.get(f"/api/boletins/{replaced}/fotos").status_code == 200
    assert len(storage.objects) == 2


def test_invalid_photo(client):
    assert (
        client.post(
            "/api/boletins/fotos/preview", files={"files": ("bu.jpg", b"bad", "image/jpeg")}
        ).status_code
        == 422
    )


def test_manual_does_not_count_as_complete_section(client, pdf):
    body = payload(pdf)
    body["municipio"] = {"codigo": "07234", "nome": "Bacabal"}
    body["eleicao"]["data"] = "2026-10-04"
    save(client, body)
    overview = client.get("/api/acompanhamento").json()
    assert overview["boletins_manuais"] == 1
    assert overview["secoes_apuradas"] == 0
    assert overview["secoes_principais_apuradas"] == 0
    assert overview["cargos"][0]["candidatos"][0]["votos"] == body["candidatos"][0]["votos"]
