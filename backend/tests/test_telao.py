import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.core.telao_access import require_admin_network
from app.models import Boletim, CandidatoVoto, Resultado, TelaoCandidato, TelaoConfig
from app.schemas.boletim import Candidato, ResultadoVaga
from app.services import divulgacao_service
from app.services.telao_realtime import ScreenEvents
from tests.acompanhamento_fixture import bacabal_text
from tests.multicargo_fixture import render_pdf
from app.services.pdf_reader import extract_text_from_pdf
from tests.test_acompanhamento import cargo, seed
from tests.test_section_registry import confirm_list, preview_list

ADMIN = {"X-Telao-Admin": "1"}


def configuration(client):
    response = client.get("/api/telao/config", headers=ADMIN)
    assert response.status_code == 200, response.text
    return response.json()


def save(client, candidates, version=None, **options):
    body = {
        "versao": configuration(client)["versao"] if version is None else version,
        "cards_por_pagina": 6,
        "tempo_rotacao_segundos": 10,
        "ativo": True,
        "candidatos": [{"cargo": office, "numero": number} for office, number in candidates],
        **options,
    }
    return client.put("/api/telao/config", headers=ADMIN, json=body)


def screen(client):
    response = client.get("/api/divulgacao")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_empty_screen_read_only_and_no_percentages(client, engine):
    data = screen(client)
    assert data["candidatos"] == []
    assert data["boletins_recebidos"] == data["secoes_representadas"] == 0
    assert data["total_secoes_esperadas"] is None
    assert data["zona"] == "0013" and data["municipio"] == "BACABAL"
    assert data["eleicao_data"] == "2026-10-04"
    assert not any("percent" in key for key in data)
    assert client.post("/api/divulgacao", json={}).status_code == 405
    assert client.delete("/api/divulgacao").status_code == 405
    assert configuration(client)["versao"] == 0
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(TelaoConfig)) == 0


def test_manual_selection_zero_votes_multiple_offices_and_no_rank(client, engine, pdf):
    seed(
        engine,
        pdf,
        cargos=[
            cargo("SENADOR", "123", 10),
            cargo("GOVERNADOR", "40", 90),
            cargo("PRESIDENTE", "40", 999),
        ],
    )
    seed(engine, pdf, section="0002", cargos=[cargo("SENADOR", "456", 0)])
    seed(engine, pdf, section="0003", cargos=[cargo("SENADOR", "789", 3)])
    desired = [("SENADOR", "456"), ("GOVERNADOR", "40"), ("SENADOR", "123"), ("SENADOR", "789")]
    response = save(client, desired)
    assert response.status_code == 200, response.text
    first = screen(client)
    assert [(c["cargo"], c["numero"]) for c in first["candidatos"]] == desired
    assert [c["votos"] for c in first["candidatos"]] == [0, 90, 10, 3]
    assert [c["ordem"] for c in first["candidatos"]] == [1, 2, 3, 4]
    seed(engine, pdf, section="0004", cargos=[cargo("SENADOR", "789", 3000)])
    second = screen(client)
    assert [(c["cargo"], c["numero"], c["id"]) for c in second["candidatos"]] == [
        (c["cargo"], c["numero"], c["id"]) for c in first["candidatos"]
    ]
    assert second["candidatos"][-1]["votos"] == 3003
    assert all(
        set(c) == {"id", "ordem", "cargo", "numero", "nome", "votos"} for c in second["candidatos"]
    )


def test_geographic_election_scope_and_coverage_never_multiply_votes(client, engine, pdf):
    seed(engine, pdf, section="0010", cargos=[cargo("GOVERNADOR", "40", 10)])
    seed(
        engine,
        pdf,
        section="0020",
        aggregated=["0021", "0022"],
        cargos=[cargo("GOVERNADOR", "40", 20)],
    )
    for index, kwargs in enumerate(
        [
            {"municipality": "76678"},
            {"zone": "0066"},
            {"day": date(2022, 10, 2)},
            {"turn": 2},
            {"day": date(2026, 10, 2)},
        ]
    ):
        seed(
            engine, pdf, section=str(30 + index), cargos=[cargo("GOVERNADOR", "40", 1000)], **kwargs
        )
    assert save(client, [("GOVERNADOR", "40")]).status_code == 200
    data = screen(client)
    assert data["boletins_recebidos"] == 2
    assert data["secoes_representadas"] == 4
    assert data["candidatos"][0]["votos"] == 30
    assert (
        client.get("/api/divulgacao?zona=0066&municipio=76678&data=2022-10-02").json()[
            "candidatos"
        ][0]["votos"]
        == 30
    )
    assert confirm_list(client, preview_list(client)).status_code == 200
    assert (
        screen(client)["total_secoes_esperadas"] == 4
    )  # The registry has one more section in zone 0066.


def test_canonical_scope_numbers_and_search_do_not_duplicate_candidates(client, engine, pdf):
    seed(
        engine,
        pdf,
        municipality="7234",
        zone="13",
        cargos=[cargo("DEPUTADO FEDERAL", "0123", 0, "JOÃO TESTE")],
    )
    seed(engine, pdf, section="0002", cargos=[cargo("DEPUTADO FEDERAL", "0123", 5, "JOÃO TESTE")])
    seed(engine, pdf, zone="0066", cargos=[cargo("DEPUTADO FEDERAL", "9999", 90, "OUTRA ZONA")])
    url = "/api/telao/candidatos-disponiveis"
    data = client.get(
        url, headers=ADMIN, params={"cargo": " deputado  federal ", "q": "joão"}
    ).json()
    assert len(data["candidatos"]) == 1
    assert data["candidatos"][0]["numero"] == "0123"
    assert data["tem_mais"] is False
    assert (
        client.get(url, headers=ADMIN, params={"cargo": "DEPUTADO FEDERAL", "q": "%"}).json()[
            "candidatos"
        ]
        == []
    )
    assert save(client, [("DEPUTADO FEDERAL", "0123")]).status_code == 200
    assert screen(client)["candidatos"][0]["votos"] == 5


def test_save_requires_real_scoped_candidates_and_validates_input(client, engine, pdf):
    seed(engine, pdf, zone="0066", cargos=[cargo("SENADOR", "123")])
    assert save(client, [("SENADOR", "123")]).status_code == 422
    assert save(client, [("SENADOR", "000")]).status_code == 422
    for options in (
        {"cards_por_pagina": 0},
        {"cards_por_pagina": 13},
        {"tempo_rotacao_segundos": 0},
        {"zona": "0066"},
    ):
        assert save(client, [], **options).status_code == 422
    seed(engine, pdf, cargos=[cargo("SENADOR", "123")])
    assert save(client, [("SENADOR", "123"), ("SENADOR", "123")]).status_code == 422
    assert screen(client)["candidatos"] == []


def test_removal_reorder_and_inactive_only_change_screen(client, engine, pdf):
    seed(engine, pdf, cargos=[cargo("PRESIDENTE", "13"), cargo("GOVERNADOR", "40")])
    selected = [("PRESIDENTE", "13"), ("GOVERNADOR", "40")]
    assert save(client, selected).status_code == 200
    ids = {c["numero"]: c["id"] for c in screen(client)["candidatos"]}
    assert save(client, selected[::-1]).status_code == 200
    assert [c["numero"] for c in screen(client)["candidatos"]] == ["40", "13"]
    assert {c["numero"]: c["id"] for c in screen(client)["candidatos"]} == ids
    assert (
        save(
            client, [], candidatos=[{"cargo": "PRESIDENTE", "numero": "13", "ativo": False}]
        ).status_code
        == 200
    )
    assert screen(client)["candidatos"] == []
    assert configuration(client)["candidatos"][0]["ativo"] is False
    assert save(client, selected, ativo=False).status_code == 200
    assert screen(client)["candidatos"] == []
    assert save(client, []).status_code == 200
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Boletim)) == 1
        assert db.scalar(select(func.count()).select_from(Resultado)) == 2
        assert db.scalar(select(func.sum(CandidatoVoto.votos))) == 20
        assert db.scalar(select(func.count()).select_from(TelaoCandidato)) == 0


def test_selection_survives_bulletin_deletion_with_zero_votes(client, engine, pdf):
    seed(engine, pdf, cargos=[cargo("GOVERNADOR", "40")])
    assert save(client, [("GOVERNADOR", "40")]).status_code == 200
    before = screen(client)["candidatos"][0]
    with engine.begin() as conn:
        conn.execute(delete(Boletim))
    after = screen(client)["candidatos"][0]
    assert after == {**before, "votos": 0}
    assert configuration(client)["candidatos"][0]["candidato_id"] is None
    assert save(client, [("GOVERNADOR", "40")]).status_code == 200


def test_concurrent_configuration_uses_version_lock(client):
    def update(cards):
        return save(client, [], version=0, cards_por_pagina=cards).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, [2, 6])) == [200, 409]
    assert configuration(client)["versao"] == 1


def test_senate_seats_not_added_again_to_overall(client, engine, pdf):
    office = cargo("SENADOR", "123", 30)
    office.vagas = [
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
    seed(engine, pdf, cargos=[office])
    office.candidatos = []
    office.votos_nominais = office.total_apurado = None
    seed(engine, pdf, section="0002", cargos=[office])
    assert save(client, [("SENADOR", "123")]).status_code == 200
    assert screen(client)["candidatos"][0]["votos"] == 60


def test_only_successfully_confirmed_imports_change_screen(client, pdf, storage):
    document = render_pdf(bacabal_text(extract_text_from_pdf(pdf), "0001", ["0002", "0003"]))
    response = client.post(
        "/api/boletins/preview", files={"file": ("test.pdf", document, "application/pdf")}
    )
    preview = response.json()
    assert preview["status"] == "OK"
    assert screen(client)["boletins_recebidos"] == 0
    storage.fail = True
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": preview["preview_token"]}
        ).status_code
        == 502
    )
    assert screen(client)["boletins_recebidos"] == 0
    storage.fail = False
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": preview["preview_token"]}
        ).status_code
        == 201
    )
    assert save(client, [("PRESIDENTE", "13")]).status_code == 200
    data = screen(client)
    assert data["boletins_recebidos"] == 1 and data["secoes_representadas"] == 3
    assert data["candidatos"][0]["votos"] == 30
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": preview["preview_token"]}
        ).status_code
        == 409
    )
    inconsistent = render_pdf(
        bacabal_text(extract_text_from_pdf(pdf), "0004", []).replace(
            "Total de votos Nominais 0030", "Total de votos Nominais 0031"
        )
    )
    bad = client.post(
        "/api/boletins/preview", files={"file": ("bad.pdf", inconsistent, "application/pdf")}
    ).json()
    assert bad["status"] == "INCONSISTENTE"
    assert (
        client.post(
            "/api/boletins/confirmar", json={"preview_token": bad["preview_token"]}
        ).status_code
        == 422
    )
    assert screen(client)["candidatos"] == data["candidatos"]


def test_snapshot_during_concurrent_import(client, engine, pdf, monkeypatch):
    seed(engine, pdf, cargos=[cargo("SENADOR", "123", 10)])
    assert save(client, [("SENADOR", "123")]).status_code == 200
    load = divulgacao_service._bulletins

    def import_after_read(db):
        rows = load(db)
        seed(engine, pdf, section="0002", cargos=[cargo("SENADOR", "123", 20)])
        return rows

    monkeypatch.setattr(divulgacao_service, "_bulletins", import_after_read)
    data = screen(client)
    assert data["boletins_recebidos"] == data["secoes_representadas"] == 1
    assert data["candidatos"][0]["votos"] == 10
    monkeypatch.setattr(divulgacao_service, "_bulletins", load)
    assert screen(client)["candidatos"][0]["votos"] == 30


@pytest.mark.parametrize("headers", [{"Authorization": ""}, {"Authorization": "Bearer invalid"}])
def test_administrative_routes_reject_untrusted_requests(client, headers):
    assert client.get("/api/telao/config", headers=headers).status_code == 401
    assert client.put("/api/telao/config", headers=headers, json={}).status_code == 401
    assert client.get("/api/divulgacao", headers=headers).status_code == 200


def test_admin_access_requires_login_even_on_private_network():
    request = Request(
        {"type": "http", "client": ("127.0.0.1", 50000), "headers": [(b"x-telao-admin", b"1")]}
    )
    with pytest.raises(HTTPException) as exc:
        require_admin_network(request)
    assert exc.value.status_code == 401


def test_new_tables_are_private_and_have_only_configuration_rows(client, engine):
    assert save(client, []).status_code == 200
    with engine.connect() as conn:
        for table in ("telao_config", "telao_candidatos"):
            assert (
                conn.scalar(
                    text("SELECT relrowsecurity FROM pg_class WHERE oid = CAST(:name AS regclass)"),
                    {"name": table},
                )
                is True
            )


def test_realtime_relays_only_invalidation_and_filters_scope():
    async def run():
        hub = ScreenEvents()
        await hub.start()
        queue = asyncio.Queue(maxsize=1)
        hub.listeners.add(queue)
        record = {
            "municipio_codigo": "07234",
            "zona": "0013",
            "eleicao_turno": 1,
            "eleicao_data": "2026-10-04",
        }
        hub.on_change({"data": {"table": "boletins", "record": {**record, "zona": "0066"}}})
        await asyncio.sleep(0)
        assert queue.empty()
        for _ in range(3):
            hub.on_change({"data": {"table": "boletins", "record": record}})
        await asyncio.sleep(0)
        assert queue.qsize() == 1 and await queue.get() == 3
        hub.on_change({"data": {"table": "telao_config", "record": {"id": 1}}})
        await asyncio.sleep(0)
        assert await queue.get() == 4
        hub.on_change({"data": {"table": "votos_candidatos", "record": {}}})
        await asyncio.sleep(0)
        assert queue.empty()
        await hub.stop()

    asyncio.run(run())
