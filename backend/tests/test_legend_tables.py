import re

import pytest

from app.services.bu_parser import parse_bu_text
from app.services.pdf_reader import extract_text_from_pdf
from app.services.validator import validate_bu
from tests.multicargo_fixture import document_text, render_pdf


@pytest.fixture
def source(pdf):
    text = document_text(extract_text_from_pdf(pdf))
    text = re.sub(r"Código (?:de )?identificação UE", "Urna efetivada", text)
    text = text.replace("ANA CLÁUDIA", "DRª ANA CLÁUDIA")
    return text.replace(
        "Total de votos Nominais 0015",
        "Votos de legenda\nPDT 12 0001\nPSD 55 0001\nEleitores aptos 0626\n"
        "Total de votos Nominais 0015",
    ).replace(
        "Total de votos Nominais 0018",
        "Votos de legenda\nMDB 15 0001\nTotal de votos Nominais 0018",
    )


def test_urn_alias_honorific_and_parties_are_separate_from_candidates(source):
    data = parse_bu_text(source)
    assert data.urna.codigo_identificacao == "01586544"
    federal, estadual = data.cargos[:2]
    assert [c.numero for c in federal.candidatos] == ["0123", "5678"]
    assert federal.candidatos[0].nome == "DRª ANA CLÁUDIA"
    assert federal.votos_nominais == 15
    assert federal.votos_legenda == 2
    assert estadual.votos_nominais == 18
    assert estadual.votos_legenda == 1
    assert data.cargos[-1].votos_legenda == 0
    assert validate_bu(data) == []


def test_wrapped_party_rows_and_repeated_legend_heading(source):
    data = parse_bu_text(
        source.replace(
            "PDT 12 0001\nPSD 55 0001",
            "PDT\n12\n0001\f\nVotos de legenda\nPSD\n55\n0001",
        )
    )
    assert data.cargos[0].votos_legenda == 2
    assert validate_bu(data) == []


def test_legend_total_on_next_line_is_not_a_party_table(source):
    data = parse_bu_text(source.replace("Votos de legenda 0002", "Votos de legenda\n0002"))
    assert data.cargos[0].votos_legenda == 2
    assert validate_bu(data) == []


def test_party_rows_do_not_supply_an_absent_total(source):
    data = parse_bu_text(source.replace("Votos de legenda 0002\n", ""))
    assert data.cargos[0].votos_legenda is None
    assert any("legenda" in p and "DEPUTADO FEDERAL" in p for p in validate_bu(data))


@pytest.mark.parametrize(
    "rows,problem",
    [
        ("PDT 12 0001\nPSD 55 0002", "soma dos votos dos partidos"),
        ("PDT 12 0001\nPDT 012 0001", "números de partido repetidos"),
    ],
)
def test_invalid_party_table_cannot_be_accepted(source, rows, problem):
    data = parse_bu_text(source.replace("PDT 12 0001\nPSD 55 0001", rows))
    assert any(problem in p for p in validate_bu(data))


def test_unrecognized_party_row_is_not_discarded(source):
    with pytest.raises(ValueError, match="linhas de legenda não reconhecidas"):
        parse_bu_text(source.replace("PDT 12 0001", "PDT 12 ilegivel"))


def test_conflicting_urn_labels_are_rejected(source):
    with pytest.raises(ValueError, match="identificações da urna conflitantes"):
        parse_bu_text(
            source.replace("Urna efetivada", "Código identificação UE 99999\nUrna efetivada")
        )


def test_party_table_pdf_persistence(client, source):
    pdf = render_pdf(source)
    response = client.post(
        "/api/boletins/preview", files={"file": ("legendas.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["status"] == "OK", preview["problemas"]
    saved = client.post("/api/boletins/confirmar", json={"preview_token": preview["preview_token"]})
    assert saved.status_code == 201, saved.text
    detail = client.get("/api/boletins/" + saved.json()["id"]).json()
    assert detail["dados"]["urna"]["codigo_identificacao"] == "01586544"
    offices = {c["nome"]: c for c in detail["cargos"]}
    federal = offices["DEPUTADO FEDERAL"]
    assert federal["votos_legenda"] == 2
    assert {c["numero"] for c in federal["candidatos"]} == {"0123", "5678"}
    assert offices["DEPUTADO ESTADUAL"]["votos_legenda"] == 1
