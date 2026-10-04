from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TelaoCandidato
from app.schemas.boletim import Candidato, ResultadoVaga
from tests.test_acompanhamento import cargo, seed
from tests.test_manual_bulletins import payload, save as save_manual
from tests.test_telao import configuration, save, screen


def test_manual_and_pdf_numbers_share_votes_and_selection(client, engine, pdf):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", "12", 10)])
    body = payload(pdf)
    body.update(
        municipio={"codigo": "07234", "nome": "Bacabal"},
        zona="0013",
        secao="0002",
        secoes_agregadas=[],
        candidatos=[{"cargo": "PRESIDENTE", "numero": "012", "nome": "TESTE", "votos": 20}],
    )
    body["eleicao"]["data"] = "2026-10-04"
    save_manual(client, body)
    candidates = client.get("/api/acompanhamento").json()["cargos"][0]["candidatos"]
    assert len(candidates) == 1
    assert candidates[0]["votos"] == 30
    available = client.get(
        "/api/telao/candidatos-disponiveis",
        params={
            "cargo": "PRESIDENTE",
            "q": "0012",
        },
    ).json()["candidatos"]
    assert len(available) == 1
    assert save(client, [("PRESIDENTE", "00012")]).status_code == 200
    original = configuration(client)["candidatos"][0]
    assert screen(client)["candidatos"][0]["votos"] == 30
    assert save(client, [("PRESIDENTE", "12")]).status_code == 200
    assert configuration(client)["candidatos"][0]["id"] == original["id"]
    assert save(client, [("PRESIDENTE", "12"), ("PRESIDENTE", "012")]).status_code == 422


def test_legacy_padded_selection_keeps_id_and_photo(client, engine, pdf):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", "12", 10)])
    assert save(client, [("PRESIDENTE", "12")]).status_code == 200
    with Session(engine) as db, db.begin():
        entry = db.scalar(select(TelaoCandidato))
        entry.numero_candidato = "0012"
        entry.foto_bucket = "candidatos"
        entry.foto_path = "existing.jpg"
        entry_id = entry.id
    assert screen(client)["candidatos"][0]["votos"] == 10
    assert save(client, [("PRESIDENTE", "12")]).status_code == 200
    with Session(engine) as db:
        entries = db.scalars(select(TelaoCandidato)).all()
        assert len(entries) == 1
        assert entries[0].id == entry_id
        assert entries[0].foto_path == "existing.jpg"


def test_senate_overall_and_padded_seats_are_not_added_twice(client, engine, pdf):
    office = cargo("SENADOR", "123", 30)
    office.vagas = [
        ResultadoVaga(
            identificacao="1",
            candidatos=[Candidato(numero="0123", nome="TESTE", votos=30)],
            votos_nominais=30,
            brancos=0,
            nulos=0,
            total_apurado=30,
        )
    ]
    seed(engine, pdf, cargos=[office])
    candidates = client.get("/api/acompanhamento").json()["cargos"][0]["candidatos"]
    assert len(candidates) == 1
    assert candidates[0]["votos"] == 30
    assert save(client, [("SENADOR", "00123")]).status_code == 200
    assert screen(client)["candidatos"][0]["votos"] == 30


def test_zero_and_twenty_digit_numbers_do_not_overflow(client, engine, pdf):
    for section, number in enumerate(["0", "000", "99999999999999999999"], 1):
        seed(engine, pdf, section=str(section), cargos=[cargo("PRESIDENTE", number, 5)])
    candidates = client.get("/api/acompanhamento").json()["cargos"][0]["candidatos"]
    assert {int(c["numero"]): c["votos"] for c in candidates} == {0: 10, 99999999999999999999: 5}
    assert (
        save(client, [("PRESIDENTE", "00"), ("PRESIDENTE", "99999999999999999999")]).status_code
        == 200
    )
    assert [c["votos"] for c in screen(client)["candidatos"]] == [10, 5]
