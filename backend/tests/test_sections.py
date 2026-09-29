import re

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Boletim, BoletimSecao
from app.services.bu_parser import parse_bu_text
from app.services.pdf_reader import extract_text_from_pdf
from app.services.validator import validate_bu
from tests.multicargo_fixture import render_pdf

MISMATCH = (
    "Quantidade de seções agregadas informada no boletim não corresponde à quantidade identificada."
)


def standalone_text(reference: str, section="0123", omit_count=False) -> str:
    source = re.sub(r"(Seção Eleitoral\s+)\d+", lambda m: m[1] + section, reference)
    source = re.sub(
        r"Quantidade de seções agregadas\s+\d+",
        "" if omit_count else "Quantidade de seções agregadas 0000",
        source,
    )
    return re.sub(r"Seções Agregadas:[\d\s]+", "", source)


@pytest.fixture
def reference(pdf):
    return extract_text_from_pdf(pdf)


def test_real_aggregated_sections_and_computed_total(reference):
    data = parse_bu_text(reference)
    assert data.secao == "0483"
    assert data.quantidade_secoes_agregadas == 4
    assert data.secoes_agregadas == ["0486", "0941", "0488", "1123"]
    assert data.total_secoes_representadas == 5
    assert data.model_dump()["total_secoes_representadas"] == 5
    assert validate_bu(data) == []


@pytest.mark.parametrize("mode", ["explicit_zero", "empty_list", "absent_both"])
def test_standalone_section_is_valid(reference, mode):
    source = standalone_text(reference, omit_count=mode == "absent_both")
    if mode == "empty_list":
        source = source.replace(
            "Quantidade de seções agregadas 0000",
            "Quantidade de seções agregadas 0000\nSeções Agregadas:\n",
        )
    data = parse_bu_text(source)
    assert data.secao == "0123"
    assert data.quantidade_secoes_agregadas == 0
    assert data.secoes_agregadas == []
    assert data.total_secoes_representadas == 1
    assert validate_bu(data) == []


@pytest.mark.parametrize("mode", ["short_list", "zero_with_list", "positive_without_list"])
def test_mismatches_not_silently_ignored(reference, mode):
    source = reference
    if mode == "short_list":
        source = source.replace("0486 0941 0488 1123", "0486 0941 0488")
    elif mode == "zero_with_list":
        source = re.sub(r"(Quantidade de seções agregadas\s+)0004", lambda m: m[1] + "0000", source)
    else:
        source = re.sub(r"Seções Agregadas:[\d\s]+", "", source)
    data = parse_bu_text(source)
    assert MISMATCH in validate_bu(data)
    if mode == "zero_with_list":
        assert data.secoes_agregadas == ["0486", "0941", "0488", "1123"]


def test_missing_count_with_nonempty_list_is_not_inferred(reference):
    source = re.sub(r"Quantidade de seções agregadas\s+\d+", "", reference)
    with pytest.raises(ValueError, match="sem quantidade"):
        parse_bu_text(source)


def test_ambiguous_principal_is_not_assumed_standalone(reference):
    source = standalone_text(reference, omit_count=True) + "\nSeção Eleitoral 0456\n"
    with pytest.raises(ValueError, match="única seção principal"):
        parse_bu_text(source)


def preview(client, source):
    response = client.post(
        "/api/boletins/preview",
        files={"file": ("section.pdf", render_pdf(source), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("aggregated,omit_count", [(True, False), (False, False), (False, True)])
def test_persistence_always_includes_principal(client, reference, engine, aggregated, omit_count):
    source = reference if aggregated else standalone_text(reference, omit_count=omit_count)
    p = preview(client, source)
    assert p["status"] == "OK"
    total = 5 if aggregated else 1
    assert p["dados"]["total_secoes_representadas"] == total
    response = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert response.status_code == 201, response.text
    detail = client.get(f"/api/boletins/{response.json()['id']}").json()
    assert detail["dados"]["total_secoes_representadas"] == total
    assert client.get("/api/boletins").json()[0]["total_secoes_representadas"] == total
    with Session(engine) as db:
        b = db.scalar(select(Boletim))
        assert b.total_secoes_representadas == total
        rows = db.scalars(select(BoletimSecao)).all()
        assert len(rows) == total
        assert len([s for s in rows if s.tipo == "PRINCIPAL"]) == 1
        assert {s.numero_secao for s in rows} == (
            {"0483", "0486", "0941", "0488", "1123"} if aggregated else {"0123"}
        )


def test_inconsistent_sections_block_confirmation(client, reference, engine, storage):
    p = preview(client, reference.replace("0486 0941 0488 1123", "0486 0941 0488"))
    assert p["status"] == "INCONSISTENTE"
    assert MISMATCH in p["problemas"]
    response = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert response.status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(Boletim.id)) is None
        assert db.scalar(select(BoletimSecao.id)) is None
    assert not storage.objects


@pytest.mark.parametrize("mode", ["principal", "previously_aggregated", "incoming_aggregated"])
def test_section_conflicts_both_directions(client, reference, engine, mode):
    existing = (
        reference if mode == "previously_aggregated" else standalone_text(reference, section="0486")
    )
    incoming = (
        reference
        if mode == "incoming_aggregated"
        else standalone_text(reference, section="0486", omit_count=True)
    )
    first = preview(client, existing)
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": first["preview_token"]}
        ).status_code
        == 201
    )
    second = preview(client, incoming)
    assert second["hash"] != first["hash"]
    response = client.post(
        "/api/boletins/confirmar", json={"preview_token": second["preview_token"]}
    )
    assert response.status_code == 409
    assert "seções" in response.json()["detail"]
    with Session(engine) as db:
        assert len(db.scalars(select(Boletim)).all()) == 1
