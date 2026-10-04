import csv
from io import StringIO
from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Boletim
from tests.test_acompanhamento import cargo, seed


def test_report_excludes_partial_and_other_elections_and_groups_sections(client, engine, pdf):
    seed(
        engine,
        pdf,
        aggregated=["0002"],
        cargos=[cargo("PRESIDENTE", "01", 10), cargo("GOVERNADOR", "02", 50)],
    )
    seed(engine, pdf, section="0003", cargos=[cargo("PRESIDENTE", "02", 30)])
    seed(engine, pdf, section="0004", cargos=[cargo("PRESIDENTE", "01", 90)])
    with Session(engine) as db, db.begin():
        db.execute(update(Boletim).where(Boletim.secao == "0004").values(origem="MANUAL"))
    seed(
        engine, pdf, section="0005", day=date(2022, 10, 2), cargos=[cargo("PRESIDENTE", "01", 100)]
    )
    report = client.get("/api/acompanhamento/relatorio").json()
    assert len(report["linhas"]) == 2
    assert report["linhas"][0]["agregadas"] == ["0002"]
    response = client.get(
        "/api/acompanhamento/relatorio.csv", params={"cargo": "PRESIDENTE", "candidatos": ["001"]}
    )
    assert response.status_code == 200
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert len(rows) == 3
    assert len(rows[0]) == 4
    assert rows[1][-1] == "10"
    assert rows[2][-1] == "0"
    assert rows[1][2] == "0002"
    assert (
        client.get(
            "/api/acompanhamento/relatorio.csv",
            params={"cargo": "PRESIDENTE", "candidatos": ["99"]},
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/acompanhamento/relatorio.csv",
            params={"cargo": "PRESIDENTE", "candidatos": ["invalid"]},
        ).status_code
        == 422
    )


def test_report_does_not_double_count_seat_votes(client, engine, pdf):
    from app.schemas.boletim import Candidato, ResultadoVaga

    senate = cargo("SENADOR", "123", 30)
    senate.vagas = [
        ResultadoVaga(
            identificacao=f"VAGA {i}",
            candidatos=[Candidato(numero="123", nome="TESTE", votos=v)],
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
    seed(engine, pdf, section="0003", cargos=[senate])
    report = client.get("/api/acompanhamento/relatorio").json()
    assert [row["cargos"]["SENADOR"]["123"] for row in report["linhas"]] == [30, 30]


def test_mixed_offices_keep_same_number_separate_and_missing_office_blank(client, engine, pdf):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", "01", 10), cargo("GOVERNADOR", "01", 50)])
    seed(engine, pdf, section="0003", cargos=[cargo("PRESIDENTE", "02", 30)])
    response = client.post(
        "/api/acompanhamento/relatorio.csv",
        json={
            "candidatos": [
                {"cargo": "PRESIDENTE", "numero": "01"},
                {"cargo": "GOVERNADOR", "numero": "01"},
                {"cargo": "PRESIDENTE", "numero": "02"},
            ],
        },
    )
    assert response.status_code == 200
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert len(rows[0]) == 6
    assert "PRESIDENTE" in rows[0][3]
    assert "GOVERNADOR" in rows[0][4]
    assert rows[1][3:] == ["10", "50", "0"]
    assert rows[2][3:] == ["0", "", "30"]
    assert (
        client.post("/api/acompanhamento/relatorio.csv", json={"candidatos": []}).status_code == 422
    )
    assert (
        client.post(
            "/api/acompanhamento/relatorio.csv",
            json={
                "candidatos": [{"cargo": "GOVERNADOR", "numero": "99"}],
            },
        ).status_code
        == 422
    )
