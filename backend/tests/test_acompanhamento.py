from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from app.schemas.boletim import Cargo, Candidato, ResultadoVaga
from app.services.acompanhamento import ELEICAO_DATA, MUNICIPIO_CODIGO
from app.services import acompanhamento
from app.services.boletim_service import make_boletim
from app.services.bu_parser import parse_bu_text
from app.services.pdf_reader import extract_text_from_pdf
from tests.acompanhamento_fixture import bacabal_text
from tests.multicargo_fixture import render_pdf


def seed(
    engine,
    pdf,
    section="0001",
    aggregated=(),
    municipality=MUNICIPIO_CODIGO,
    day=ELEICAO_DATA,
    turn=1,
    cargos=None,
    zone="0013",
):
    data = parse_bu_text(extract_text_from_pdf(pdf))
    data.municipio.codigo = municipality
    data.municipio.nome = "BACABAL"
    data.eleicao.data = day
    data.eleicao.turno = turn
    data.zona = zone
    data.secao = section
    data.secoes_agregadas = list(aggregated)
    data.quantidade_secoes_agregadas = len(aggregated)
    if cargos is not None:
        data.cargos = cargos
    with Session(engine) as db, db.begin():
        db.add(make_boletim(data, "synthetic-test.pdf", uuid4().hex * 2, "test", "test.pdf"))


def cargo(name, number="01", votes=10, candidate="CANDIDATO TESTE"):
    return Cargo(
        nome=name,
        candidatos=[Candidato(numero=number, nome=candidate, votos=votes)],
        votos_nominais=votes,
        votos_legenda=0,
        brancos=0,
        nulos=0,
        total_apurado=votes,
    )


def test_empty_overview(client):
    response = client.get("/api/acompanhamento")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["municipio"] == {"nome": "Bacabal", "uf": "MA", "codigo": "07234"}
    assert data["eleicao"] == {"ano": 2026, "turno": 1, "data": "2026-10-04"}
    assert data["boletins"] == data["secoes_apuradas"] == 0
    assert data["secoes_esperadas"] is data["secoes_pendentes"] is None
    assert data["ultima_importacao"] is None
    assert data["cargos"] == data["secoes"] == []
    assert data["eleicao_configurada"] == data["eleicao"]
    assert data["datas_disponiveis"] == [{"data": "2026-10-04", "boletins": 0}]


def test_import_during_overview_is_visible_only_on_next_refresh(client, engine, pdf, monkeypatch):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE")])
    load = acompanhamento._load_bulletins

    def import_after_snapshot(db, election_date=ELEICAO_DATA):
        rows = load(db, election_date)
        seed(engine, pdf, section="0002", cargos=[cargo("PRESIDENTE", votes=20)])
        return rows

    monkeypatch.setattr(acompanhamento, "_load_bulletins", import_after_snapshot)
    data = client.get("/api/acompanhamento").json()
    assert data["boletins"] == data["secoes_apuradas"] == 1
    assert data["cargos"][0]["boletins"] == 1
    assert data["cargos"][0]["candidatos"][0]["votos"] == 10
    assert data["datas_disponiveis"] == [{"data": "2026-10-04", "boletins": 1}]
    monkeypatch.setattr(acompanhamento, "_load_bulletins", load)
    data = client.get("/api/acompanhamento").json()
    assert data["boletins"] == data["secoes_apuradas"] == 2
    assert data["cargos"][0]["candidatos"][0]["votos"] == 30


def test_office_without_candidates_is_not_dropped(client, engine, pdf):
    office = cargo("PRESIDENTE", votes=0)
    office.candidatos = []
    seed(engine, pdf, cargos=[office])
    assert client.get("/api/acompanhamento").json()["cargos"] == [
        {"nome": "PRESIDENTE", "boletins": 1, "candidatos": []}
    ]


def test_scope_does_not_mix_municipalities_years_turns_or_dates(client, engine, pdf):
    seed(engine, pdf, municipality="76678")
    seed(engine, pdf, day=date(2022, 10, 2))
    seed(engine, pdf, turn=2)
    seed(engine, pdf, day=date(2026, 11, 1))
    seed(engine, pdf, municipality="7234")
    data = client.get("/api/acompanhamento").json()
    assert data["boletins"] == data["secoes_apuradas"] == 1
    assert data["cargos"][0]["candidatos"][0]["votos"] == 103


def test_other_date_is_discoverable_without_changing_default_totals(client, engine, pdf):
    seed(
        engine,
        pdf,
        day=date(2026, 10, 2),
        section="0002",
        aggregated=["0165", "0167", "0168", "0169"],
        cargos=[cargo("PRESIDENTE", "13", 111), cargo("GOVERNADOR", "40", 84)],
    )
    default = client.get("/api/acompanhamento").json()
    assert default["boletins"] == 0
    assert default["cargos"] == []
    assert default["datas_disponiveis"] == [
        {"data": "2026-10-04", "boletins": 0},
        {"data": "2026-10-02", "boletins": 1},
    ]
    selected = client.get("/api/acompanhamento?data=2026-10-02").json()
    assert selected["eleicao"] == {"ano": 2026, "turno": 1, "data": "2026-10-02"}
    assert selected["eleicao_configurada"] == default["eleicao"]
    assert selected["boletins"] == 1
    assert selected["secoes_apuradas"] == 5
    assert {s["secao"] for s in selected["secoes"]} == {"0002", "0165", "0167", "0168", "0169"}
    offices = {c["nome"]: c for c in selected["cargos"]}
    assert offices["PRESIDENTE"]["candidatos"][0]["votos"] == 111
    assert offices["GOVERNADOR"]["candidatos"][0]["votos"] == 84
    assert client.get("/api/acompanhamento").json()["boletins"] == 0


def test_date_selection_keeps_same_candidates_and_sections_in_separate_elections(
    client, engine, pdf
):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", "13", 10)])
    seed(engine, pdf, day=date(2026, 10, 2), cargos=[cargo("PRESIDENTE", "13", 30)])
    seed(engine, pdf, day=date(2022, 10, 2), cargos=[cargo("PRESIDENTE", "13", 50)])
    for day, votes in [("2026-10-04", 10), ("2026-10-02", 30), ("2022-10-02", 50)]:
        data = client.get("/api/acompanhamento", params={"data": day}).json()
        assert data["eleicao"]["ano"] == int(day[:4])
        assert data["boletins"] == data["secoes_apuradas"] == 1
        assert data["cargos"][0]["candidatos"][0]["votos"] == votes


def test_available_dates_exclude_other_municipalities_and_turns(client, engine, pdf):
    seed(engine, pdf, day=date(2026, 10, 2), municipality="7234")
    seed(engine, pdf, day=date(2020, 1, 1), municipality="76678")
    seed(engine, pdf, day=date(2026, 11, 1), turn=2)
    assert client.get("/api/acompanhamento").json()["datas_disponiveis"] == [
        {"data": "2026-10-04", "boletins": 0},
        {"data": "2026-10-02", "boletins": 1},
    ]


def test_other_date_does_not_reuse_the_configured_section_registry(client, engine, pdf):
    response = client.post(
        "/api/acompanhamento/secoes/preview",
        files={
            "file": (
                "secoes.csv",
                b"zona;secao_principal;secoes_agregadas\n0013;0001;0002\n",
                "text/csv",
            ),
        },
    )
    preview = response.json()
    assert (
        client.post(
            "/api/acompanhamento/secoes/confirmar",
            json={
                "grupos": preview["grupos"],
                "versao_lista": preview["versao_lista"],
            },
        ).status_code
        == 200
    )
    seed(engine, pdf, day=date(2026, 10, 2), aggregated=["0002"])
    selected = client.get("/api/acompanhamento?data=2026-10-02").json()
    assert selected["boletins"] == 1
    assert selected["secoes_apuradas"] == 2
    assert selected["secoes_esperadas"] is None
    assert selected["secoes_principais_apuradas"] == 1
    assert selected["secoes_principais_esperadas"] is None
    assert selected["secoes_principais_pendentes"] is None
    assert selected["grupos_secoes"] == []
    default = client.get("/api/acompanhamento").json()
    assert default["secoes_pendentes"] == 2
    assert default["secoes_principais_apuradas"] == 0
    assert default["secoes_principais_esperadas"] == default["secoes_principais_pendentes"] == 1
    assert default["grupos_secoes"][0]["status"] == "PENDENTE"


def test_valid_date_without_imports_is_empty_and_discoverable(client):
    data = client.get("/api/acompanhamento?data=2026-10-01").json()
    assert data["boletins"] == data["secoes_apuradas"] == 0
    assert data["datas_disponiveis"] == [
        {"data": "2026-10-04", "boletins": 0},
        {"data": "2026-10-01", "boletins": 0},
    ]


def test_invalid_date_is_rejected(client):
    assert client.get("/api/acompanhamento?data=2026-02-31").status_code == 422


def test_sum_once_per_bulletin_with_aggregates_and_repeated_read(client, engine, pdf):
    seed(engine, pdf, aggregated=["0002", "0003"], cargos=[cargo("PRESIDENTE")])
    seed(
        engine,
        pdf,
        section="0004",
        cargos=[cargo("PRESIDENTE", votes=20), cargo("GOVERNADOR", votes=7)],
    )
    for _ in range(2):
        data = client.get("/api/acompanhamento").json()
        assert data["boletins"] == 2
        assert data["secoes_apuradas"] == 4
        assert len([s for s in data["secoes"] if s["tipo"] == "AGREGADA"]) == 2
        governor, president = data["cargos"]
        assert governor["candidatos"][0]["votos"] == 7
        assert president["candidatos"][0]["votos"] == 30
        assert president["candidatos"][0]["numero"] == "01"
        assert president["boletins"] == 2
    seed(engine, pdf, section="0005", cargos=[cargo("PRESIDENTE", votes=4)])
    assert client.get("/api/acompanhamento").json()["cargos"][1]["candidatos"][0]["votos"] == 34


def test_name_variations_zero_votes_and_same_section_in_another_zone(client, engine, pdf):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", candidate="NOME A")])
    seed(engine, pdf, zone="0066", cargos=[cargo("PRESIDENTE", votes=0, candidate="NOME B")])
    data = client.get("/api/acompanhamento").json()
    assert data["secoes_apuradas"] == 2
    candidate = data["cargos"][0]["candidatos"][0]
    assert candidate["votos"] == 10
    assert candidate["nomes"] == ["NOME A", "NOME B"]


def test_senate_seats_preserved_without_double_counting_overall(client, engine, pdf):
    senate = cargo("SENADOR", "123", 30)
    senate.vagas = [
        ResultadoVaga(
            identificacao=f"VAGA {i}",
            candidatos=[Candidato(numero="123", nome="CANDIDATO TESTE", votos=v)],
            votos_nominais=v,
            votos_legenda=0,
            brancos=0,
            nulos=0,
            total_apurado=v,
        )
        for i, v in [(1, 10), (2, 20)]
    ]
    seed(engine, pdf, cargos=[senate])
    senate.candidatos = []
    senate.votos_nominais = senate.total_apurado = senate.brancos = senate.nulos = None
    seed(engine, pdf, section="0002", cargos=[senate])
    candidate = client.get("/api/acompanhamento").json()["cargos"][0]["candidatos"][0]
    assert candidate["votos"] == 60
    assert candidate["vagas"] == [
        {"identificacao": None, "votos": 30},
        {"identificacao": "VAGA 1", "votos": 20},
        {"identificacao": "VAGA 2", "votos": 40},
    ]


def test_only_confirmed_imports_update_overview(client, pdf, storage):
    source = extract_text_from_pdf(pdf)
    tokens = []
    for section, aggregated in [("0001", ["0002", "0003"]), ("0004", [])]:
        document = render_pdf(bacabal_text(source, section, aggregated))
        preview = client.post(
            "/api/boletins/preview",
            files={"file": ("synthetic-test.pdf", document, "application/pdf")},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "OK", preview.text
        tokens.append(preview.json()["preview_token"])
    assert client.get("/api/acompanhamento").json()["boletins"] == 0

    # A failed upload must not change the dashboard either.
    storage.fail = True
    failed = client.post("/api/boletins/confirmar", json={"preview_token": tokens[0]})
    assert failed.status_code == 502
    assert client.get("/api/acompanhamento").json()["boletins"] == 0
    storage.fail = False

    for index, token in enumerate(tokens, start=1):
        saved = client.post("/api/boletins/confirmar", json={"preview_token": token})
        assert saved.status_code == 201, saved.text
        dashboard = client.get("/api/acompanhamento").json()
        assert dashboard["boletins"] == index
        assert dashboard["secoes_apuradas"] == index + 2
        assert dashboard["ultima_importacao"] is not None
        cargos = {cargo["nome"]: cargo for cargo in dashboard["cargos"]}
        assert cargos["PRESIDENTE"]["candidatos"][0]["votos"] == 30 * index
        assert cargos["PRESIDENTE"]["candidatos"][1]["votos"] == 0
        assert cargos["GOVERNADOR"]["candidatos"][0]["votos"] == 7 * index
        federal = cargos["DEPUTADO FEDERAL"]["candidatos"][0]
        assert federal["numero"] == "0123"
        assert federal["votos"] == 10 * index  # Party votes do not belong to a candidate.

    duplicate = client.post("/api/boletins/confirmar", json={"preview_token": tokens[0]})
    assert duplicate.status_code == 409
    assert client.get("/api/acompanhamento").json()["boletins"] == 2
