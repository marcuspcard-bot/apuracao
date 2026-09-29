import pytest
import pymupdf

from app.services.bu_parser import parse_bu_text
from app.services.file_hash import calculate_sha256
from app.services.pdf_reader import extract_text_from_pdf
from app.services.validator import validate_bu


def test_real_pdf(pdf):
    data = parse_bu_text(extract_text_from_pdf(pdf))
    assert data.municipio.model_dump() == {"codigo": "30848", "nome": "XANGAI"}
    assert (data.zona, data.local_votacao, data.secao) == ("0001", "1015", "0483")
    assert data.secoes_agregadas == ["0486", "0941", "0488", "1123"]
    assert data.quantidade_secoes_agregadas == 4
    assert data.eleitores.model_dump() == {"aptos": 626, "comparecimento": 195, "faltosos": 431}
    assert data.eleicao.model_dump(mode="json") == {
        "descricao": "Eleições Gerais 2018",
        "turno": 1,
        "data": "2018-10-07",
    }
    assert data.urna.model_dump(mode="json") == {
        "codigo_identificacao": "01586544",
        "data_abertura": "2018-10-07",
        "hora_abertura": "08:00:00",
        "data_fechamento": "2018-10-07",
        "hora_fechamento": "17:00:30",
    }
    c = data.cargos[0]
    assert c.nome == "PRESIDENTE"
    assert [(v.nome, v.numero, v.votos) for v in c.candidatos] == [
        ("CIRO GOMES", "12", 16),
        ("FERNANDO HADDAD", "13", 7),
        ("HENRIQUE MEIRELLES", "15", 1),
        ("JAIR BOLSONARO", "17", 103),
        ("MARINA SILVA", "18", 5),
        ("ALVARO DIAS", "19", 7),
        ("EYMAEL", "27", 2),
        ("JOÃO AMOÊDO", "30", 17),
        ("GERALDO ALCKMIN", "45", 13),
        ("GUILHERME BOULOS", "50", 1),
        ("CABO DACIOLO", "51", 3),
    ]
    assert (c.votos_nominais, c.brancos, c.nulos, c.total_apurado) == (175, 5, 15, 195)
    assert c.votos_legenda == 0
    assert sum(v.votos for v in c.candidatos) == 175
    assert data.eleitores.aptos - data.eleitores.comparecimento == data.eleitores.faltosos
    assert c.votos_nominais + c.brancos + c.nulos == c.total_apurado
    assert data.codigo_carga == "253.036.502.661.719.936.089.670"
    assert data.assinatura_qrcode.endswith("F81BAE08")
    assert validate_bu(data) == []


@pytest.mark.parametrize(
    "cargo",
    ["GOVERNADOR", "SENADOR", "DEPUTADO FEDERAL", "DEPUTADO ESTADUAL", "DEPUTADO DISTRITAL"],
)
def test_dynamic_offices(pdf, cargo):
    data = parse_bu_text(extract_text_from_pdf(pdf).replace("PRESIDENTE", cargo))
    assert data.cargos[0].nome == cargo
    assert validate_bu(data) == []


def test_multiple_offices(pdf):
    text = extract_text_from_pdf(pdf)
    start = text.index("-----------------------PRESIDENTE")
    end = text.index("ASSINATURA QR CODE")
    second = text[start:end].replace("PRESIDENTE", "GOVERNADOR")
    data = parse_bu_text(text[:end] + second + text[end:])
    assert [c.nome for c in data.cargos] == ["PRESIDENTE", "GOVERNADOR"]
    assert validate_bu(data) == []


@pytest.mark.parametrize("change", ["attendance", "absent", "total", "candidate", "sections"])
def test_inconsistencies(pdf, change):
    data = parse_bu_text(extract_text_from_pdf(pdf))
    if change == "attendance":
        data.eleitores.comparecimento = 900
    if change == "absent":
        data.eleitores.faltosos = 0
    if change == "total":
        data.cargos[0].total_apurado = 194
    if change == "candidate":
        data.cargos[0].candidatos[0].votos = 15
    if change == "sections":
        data.secoes_agregadas[0] = data.secao
    assert validate_bu(data)


def test_bad_and_empty_pdf():
    with pytest.raises(ValueError, match="inválido"):
        extract_text_from_pdf(b"not a PDF")
    with pymupdf.open() as doc:
        doc.new_page()
        with pytest.raises(ValueError, match="Não foi possível extrair"):
            extract_text_from_pdf(doc.tobytes())


def test_hash(pdf):
    assert len(calculate_sha256(pdf)) == 64
    assert calculate_sha256(pdf) != calculate_sha256(pdf + b"\n")


def test_signature_without_separator_and_wrapped_candidate(pdf):
    import re

    source = re.sub(r"(?m)^\s*=+\s*$", "", extract_text_from_pdf(pdf))
    source = source.replace("CIRO GOMES", "CIRO\nGOMES")
    data = parse_bu_text(source)
    assert data.assinatura_qrcode.endswith("F81BAE08")
    assert not data.assinatura_qrcode.endswith("C")
    assert data.cargos[0].candidatos[0].nome == "CIRO GOMES"
    assert validate_bu(data) == []


def test_unrecognized_candidate_line_blocks_parser(pdf):
    source = extract_text_from_pdf(pdf).replace("CIRO GOMES", "# CORRUPTED ROW #")
    with pytest.raises(ValueError, match="linhas de candidatos"):
        parse_bu_text(source)
