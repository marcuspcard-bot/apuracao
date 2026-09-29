import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Boletim, CandidatoVoto, Resultado
from app.services.bu_parser import (
    detect_office_blocks,
    parse_bu_text,
    parse_office_block,
    parse_office_totals,
)
from app.services.offices import normalize_office_name
from app.services.pdf_reader import extract_text_from_pdf
from app.services.validator import validate_bu
from tests.multicargo_fixture import OFFICES, document_text, office_text, render_pdf


@pytest.fixture
def reference(pdf):
    return extract_text_from_pdf(pdf)


@pytest.mark.parametrize("names", [OFFICES, list(reversed(OFFICES)), OFFICES[::2], OFFICES[:2]])
def test_offices_independent(reference, names):
    data = parse_bu_text(document_text(reference, names))
    assert [c.nome for c in data.cargos] == [o[0] for o in names]
    for cargo, (name, candidates, totals) in zip(data.cargos, names):
        assert [(c.numero, c.nome, c.votos) for c in cargo.candidatos] == candidates
        assert all(isinstance(c.numero, str) and isinstance(c.votos, int) for c in cargo.candidatos)
        assert (
            cargo.votos_nominais,
            cargo.votos_legenda,
            cargo.brancos,
            cargo.nulos,
            cargo.total_apurado,
        ) == totals
    assert validate_bu(data) == []


@pytest.mark.parametrize(
    "name,expected",
    [
        ("  deputado   federal  ", "DEPUTADO FEDERAL"),
        ("deputado\nDistrital", "DEPUTADO DISTRITAL"),
        ("--- senador ---", "SENADOR"),
        ("desconhecido", None),
    ],
)
def test_normalize_office(name, expected):
    assert normalize_office_name(name) == expected


def test_cross_page_repeated_headers_and_wrapping(reference):
    source = document_text(reference)
    repeat = "\fJustiça Eleitoral\nTribunal Regional Eleitoral [ZZ]\nBoletim de Urna\nPágina 2 de 4\n-- deputado federal --\nNome do\ncandidato Num cand Votos\n"
    source = source.replace("BRUNO SILVA", repeat + "BRUNO\nSILVA")
    source = source.replace("0123  0010", "0123\n0010")
    source = source.replace("DEPUTADO ESTADUAL", "deputado\n  estadual")
    source = source.replace("Brancos 0001", "Brancos\n0001")
    data = parse_bu_text(source)
    assert len(data.cargos) == 6
    assert [(c.numero, c.nome, c.votos) for c in data.cargos[0].candidatos] == OFFICES[0][1]
    assert data.cargos[1].candidatos[-1].votos == 0
    assert validate_bu(data) == []


def test_repeated_complete_document_header(reference):
    source = document_text(reference)
    prefix = source[: source.index("---------------- DEPUTADO FEDERAL")]
    source = source.replace(
        "BRUNO SILVA",
        "\f" + prefix + "DEPUTADO FEDERAL\nNome do candidato Num cand Votos\nBRUNO SILVA",
    )
    data = parse_bu_text(source)
    assert data.cargos[0].candidatos[1].nome == "BRUNO SILVA"
    assert validate_bu(data) == []


@pytest.mark.parametrize(
    "field,label",
    [
        ("votos_nominais", "Total de votos Nominais 0070"),
        ("brancos", "Brancos 0003"),
        ("nulos", "Nulos 0004"),
        ("total_apurado", "Total Apurado 0077"),
    ],
)
def test_missing_totals_do_not_borrow_from_next_office(reference, field, label):
    source = document_text(reference).replace(label, "")
    data = parse_bu_text(source)
    assert getattr(data.cargos[3], field) is None
    assert data.cargos[4].total_apurado == 153
    assert any("SENADOR" in p and field.replace("_", " ") in p for p in validate_bu(data))


def test_missing_legend_is_zero_but_malformed_is_not(reference):
    data = parse_bu_text(
        document_text(reference).replace("Votos de legenda 0002", "Votos de legenda ilegível")
    )
    assert data.cargos[0].votos_legenda is None
    assert data.cargos[-1].votos_legenda == 0
    assert any("legenda" in p for p in validate_bu(data))


def test_validation_is_per_office_and_includes_legend(reference):
    data = parse_bu_text(document_text(reference))
    data.cargos[0].candidatos[0].votos += 1
    data.cargos[1].candidatos[0].votos -= 1
    problems = validate_bu(data)
    assert len(problems) == 2
    assert "DEPUTADO FEDERAL" in problems[0]
    assert "DEPUTADO ESTADUAL" in problems[1]
    data = parse_bu_text(document_text(reference))
    data.cargos[0].votos_legenda += 1
    assert len(validate_bu(data)) == 1


def test_variable_candidate_count_and_all_zero(reference):
    candidates = [(f"{i:05}", "CANDIDATO SEM VOTOS", 0) for i in range(75)]
    data = parse_bu_text(
        document_text(reference, [("DEPUTADO ESTADUAL", candidates, (0, 0, 0, 0, 0))])
    )
    assert len(data.cargos[0].candidatos) == 75
    assert data.cargos[0].candidatos[0].numero == "00000"
    assert validate_bu(data) == []


def test_senate_seats_preserved(reference):
    source = document_text(reference, [OFFICES[3]])
    senate = office_text(OFFICES[3])
    source = source.replace(
        senate,
        senate.replace(" SENADOR ", " SENADOR - 1ª VAGA ")
        + senate.replace(" SENADOR ", " SENADOR - 2ª VAGA "),
    )
    data = parse_bu_text(source)
    cargo = data.cargos[0]
    assert cargo.nome == "SENADOR"
    assert cargo.total_apurado is None
    assert cargo.candidatos == []
    assert [v.identificacao for v in cargo.vagas] == ["1ª VAGA", "2ª VAGA"]
    assert [v.total_apurado for v in cargo.vagas] == [77, 77]
    assert validate_bu(data) == []
    cargo.vagas[0].total_apurado = None
    assert any("1ª VAGA" in p for p in validate_bu(data))


def test_block_and_total_helpers():
    blocks = detect_office_blocks(office_text(OFFICES[0]) + office_text(OFFICES[-1]))
    assert len(blocks) == 2
    assert parse_office_block(blocks[0]).votos_legenda == 2
    totals, problems = parse_office_totals("Total Apurado 20\nTotal Apurado 21", "SENADOR")
    assert totals["total_apurado"] is None
    assert any("conflitantes" in p for p in problems)


@pytest.mark.parametrize("office", ["DEPUTADO FEDERAL", "GOVERNADOR"])
def test_unknown_office_cannot_disappear(reference, office):
    source = document_text(reference).replace(office, "CARGO DESCONHECIDO")
    with pytest.raises(ValueError, match="cargo não reconhecido|cargo reconhecido"):
        parse_bu_text(source)


def test_unexpected_rows_after_totals_are_reported(reference):
    source = document_text(reference).replace(
        "Total Apurado 0021", "Total Apurado 0021\nCANDIDATO EXTRA 9999 0000"
    )
    data = parse_bu_text(source)
    assert any("Conteúdo não reconhecido" in p for p in validate_bu(data))


def test_multioffice_pdf_persistence(client, reference, engine):
    pdf = render_pdf(document_text(reference))
    response = client.post(
        "/api/boletins/preview", files={"file": ("multi.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 200, response.text
    p = response.json()
    assert p["status"] == "OK", p["problemas"]
    assert len(p["dados"]["cargos"]) == 6
    saved = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert saved.status_code == 201, saved.text
    detail = client.get(f"/api/boletins/{saved.json()['id']}").json()
    assert detail["dados_gerais"]["secao"] == "0777"
    assert detail["cargos"] == detail["dados"]["cargos"]
    results = {c["nome"]: c for c in detail["cargos"]}
    for name, candidates, totals in OFFICES:
        assert results[name]["votos_legenda"] == totals[1]
        assert sorted(
            (c["numero"], c["nome"], c["votos"]) for c in results[name]["candidatos"]
        ) == sorted(candidates)
    with Session(engine) as db:
        rows = db.execute(
            select(Resultado.cargo, CandidatoVoto.numero_candidato).join(CandidatoVoto)
        ).all()
        assert set(rows) == {
            (name, number) for name, candidates, _ in OFFICES for number, _, _ in candidates
        }


def test_incomplete_office_preview_blocks_confirmation(client, reference, engine, storage):
    pdf = render_pdf(document_text(reference).replace("Total Apurado 0077", ""))
    p = client.post(
        "/api/boletins/preview", files={"file": ("missing.pdf", pdf, "application/pdf")}
    ).json()
    assert p["status"] == "INCONSISTENTE"
    assert p["dados"]["cargos"][3]["total_apurado"] is None
    assert any("SENADOR" in problem for problem in p["problemas"])
    response = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert response.status_code == 422
    with Session(engine) as db:
        assert db.scalar(select(Boletim.id)) is None
    assert storage.objects == {}


def test_senate_seats_persistence(client, reference, engine):
    source = document_text(reference, [OFFICES[3]])
    senate = office_text(OFFICES[3])
    source = source.replace(
        senate,
        senate.replace(" SENADOR ", " SENADOR - 1ª VAGA ")
        + senate.replace(" SENADOR ", " SENADOR - 2ª VAGA "),
    )
    pdf = render_pdf(source)
    p = client.post(
        "/api/boletins/preview", files={"file": ("seats.pdf", pdf, "application/pdf")}
    ).json()
    assert p["status"] == "OK", p
    saved = client.post("/api/boletins/confirmar", json={"preview_token": p["preview_token"]})
    assert saved.status_code == 201, saved.text
    detail = client.get(f"/api/boletins/{saved.json()['id']}").json()
    assert detail["cargos"][0]["total_apurado"] is None
    assert len(detail["cargos"][0]["vagas"]) == 2
    with Session(engine) as db:
        rows = db.scalars(select(CandidatoVoto)).all()
        assert len(rows) == 4
        assert {c.vaga for c in rows} == {"1ª VAGA", "2ª VAGA"}
