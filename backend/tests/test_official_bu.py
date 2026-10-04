from pathlib import Path

import pytest

from app.services.bu_parser import parse_bu_text
from app.services.pdf_reader import extract_text_from_pdf
from app.services.validator import validate_bu


@pytest.fixture
def official_text():
    return extract_text_from_pdf((Path(__file__).parent / "fixtures/bacabal_2026.pdf").read_bytes())


def test_official_party_grouped_bu(official_text):
    data = parse_bu_text(official_text)
    assert (data.municipio.nome, data.zona, data.secao) == ("BACABAL", "0013", "0462")
    assert data.eleitores.model_dump() == {"aptos": 184, "comparecimento": 156, "faltosos": 28}
    assert [
        (c.nome, len(c.candidatos), c.votos_nominais, c.votos_legenda, c.total_apurado)
        for c in data.cargos
    ] == [
        ("DEPUTADO FEDERAL", 18, 154, 0, 156),
        ("DEPUTADO ESTADUAL", 8, 148, 6, 156),
        ("SENADOR", 7, 281, 0, 312),
        ("GOVERNADOR", 4, 146, 0, 156),
        ("PRESIDENTE", 5, 152, 0, 156),
    ]
    assert any(c.nome == "MARCOS CALDAS COLETIVO +" for c in data.cargos[1].candidatos)
    assert validate_bu(data) == []


@pytest.mark.parametrize("label", ["Votos de legenda", "Total do partido"])
def test_missing_party_subtotal_rejected(official_text, label):
    import re

    source = re.sub(rf"{label}\s+0000|{label}\s+0001", f"{label} ilegível", official_text, count=1)
    with pytest.raises(ValueError, match="subtotais do partido"):
        parse_bu_text(source)


def test_party_subtotal_mismatch_detected(official_text):
    import re

    source = re.sub(r"Total do partido\s+0001", "Total do partido 0002", official_text, count=1)
    assert any("total do partido 13" in p for p in validate_bu(parse_bu_text(source)))


def test_official_pdf_preview_and_confirmation(client):
    pdf = (Path(__file__).parent / "fixtures/bacabal_2026.pdf").read_bytes()
    response = client.post(
        "/api/boletins/preview", files={"file": ("bacabal.pdf", pdf, "application/pdf")}
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["status"] == "OK", preview["problemas"]
    saved = client.post("/api/boletins/confirmar", json={"preview_token": preview["preview_token"]})
    assert saved.status_code == 201, saved.text
    detail = client.get("/api/boletins/" + saved.json()["id"]).json()
    assert len(detail["cargos"]) == 5
