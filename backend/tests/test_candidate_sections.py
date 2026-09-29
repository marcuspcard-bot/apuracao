from datetime import date

import pytest

from app.schemas.boletim import Candidato, ResultadoVaga
from tests.test_acompanhamento import cargo, seed


def query(client, section="0001", zone="0013", day="2026-10-04"):
    response = client.get(
        "/api/acompanhamento/votos-secao",
        params={"zona": zone, "secao": section, "data": day},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_filter_counts_each_bulletin_once_for_main_and_aggregated_sections(client, engine, pdf):
    seed(
        engine,
        pdf,
        aggregated=["0002", "0003"],
        cargos=[cargo("PRESIDENTE", "01", 10), cargo("GOVERNADOR", "01", 7)],
    )
    seed(engine, pdf, section="0004", cargos=[cargo("PRESIDENTE", "01", 20)])
    main = query(client)
    assert main["boletins"] == 1
    assert {s["secao"] for s in main["secoes"]} == {"0001", "0002", "0003"}
    offices = {office["nome"]: office for office in main["cargos"]}
    assert offices["PRESIDENTE"]["candidatos"][0]["votos"] == 10
    assert offices["GOVERNADOR"]["candidatos"][0]["votos"] == 7
    assert offices["PRESIDENTE"]["candidatos"][0]["numero"] == "01"
    assert query(client, "0002") == main
    assert query(client, "0003") == main
    assert query(client, "000001", "000013") == main
    assert query(client, "0004")["cargos"][0]["candidatos"][0]["votos"] == 20
    overall = client.get("/api/acompanhamento").json()
    assert overall["boletins"] == 2
    assert overall["cargos"][1]["candidatos"][0]["votos"] == 30


def test_filter_keeps_zone_municipality_date_and_turn_separate(client, engine, pdf):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", votes=10)])
    seed(engine, pdf, zone="0066", cargos=[cargo("PRESIDENTE", votes=20)])
    seed(engine, pdf, municipality="76678", cargos=[cargo("PRESIDENTE", votes=30)])
    seed(engine, pdf, turn=2, cargos=[cargo("PRESIDENTE", votes=40)])
    seed(engine, pdf, day=date(2026, 10, 2), cargos=[cargo("PRESIDENTE", votes=50)])
    seed(engine, pdf, day=date(2022, 10, 2), cargos=[cargo("PRESIDENTE", votes=60)])
    for zone, day, votes in [
        ("0013", "2026-10-04", 10),
        ("0066", "2026-10-04", 20),
        ("0013", "2026-10-02", 50),
        ("0013", "2022-10-02", 60),
    ]:
        data = query(client, zone=zone, day=day)
        assert data["boletins"] == 1
        assert data["cargos"][0]["candidatos"][0]["votos"] == votes


def test_filter_distinguishes_missing_bulletin_empty_office_and_zero_votes(client, engine, pdf):
    assert query(client) == {"boletins": 0, "cargos": [], "secoes": []}
    empty = cargo("GOVERNADOR", votes=0)
    empty.candidatos = []
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", "01", 0), empty])
    data = query(client)
    offices = {office["nome"]: office for office in data["cargos"]}
    assert data["boletins"] == 1
    assert offices["PRESIDENTE"]["candidatos"][0]["votos"] == 0
    assert offices["GOVERNADOR"]["candidatos"] == []
    assert "SENADOR" not in offices
    assert query(client, "9999") == {"boletins": 0, "cargos": [], "secoes": []}


def test_filter_preserves_senate_seats_without_adding_them_to_overall(client, engine, pdf):
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
    seed(engine, pdf, aggregated=["0002"], cargos=[senate])
    senate.candidatos = []
    senate.votos_nominais = senate.total_apurado = senate.brancos = senate.nulos = None
    seed(engine, pdf, section="0003", cargos=[senate])
    for section in ("0001", "0002", "0003"):
        candidate = query(client, section)["cargos"][0]["candidatos"][0]
        assert candidate["votos"] == 30
        assert [v for v in candidate["vagas"] if v["identificacao"]] == [
            {"identificacao": "VAGA 1", "votos": 10},
            {"identificacao": "VAGA 2", "votos": 20},
        ]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"zona": "0013"},
        {"secao": "0001"},
        {"zona": "abc", "secao": "0001"},
        {"zona": "0013", "secao": "-1"},
        {"zona": "0013", "secao": "1.0"},
        {"zona": "0013", "secao": "1" * 21},
        {"zona": "0013", "secao": "0001", "data": "2026-02-31"},
    ],
)
def test_invalid_section_queries_are_rejected(client, params):
    assert client.get("/api/acompanhamento/votos-secao", params=params).status_code == 422
