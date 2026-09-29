from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SecaoEsperada
from app.services.secoes_esperadas import parse_sections_csv
from tests.test_acompanhamento import seed


CSV = b"zona;secao_principal;secoes_agregadas\n0013;0001;0002 0003\n0013;0004;\n0066;0001;\n"


def preview_list(client, content=CSV):
    response = client.post(
        "/api/acompanhamento/secoes/preview",
        files={
            "file": ("secoes.csv", content, "text/csv"),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm_list(client, preview):
    return client.post(
        "/api/acompanhamento/secoes/confirmar",
        json={
            "grupos": preview["grupos"],
            "versao_lista": preview["versao_lista"],
        },
    )


def test_registry_preview_and_confirmation(client, engine):
    preview = preview_list(client)
    assert preview["total_secoes"] == 5
    assert preview["substitui_lista"] is False
    assert preview["grupos"][0]["secoes_agregadas"] == ["0002", "0003"]
    assert client.get("/api/acompanhamento").json()["lista_secoes_importada"] is False
    assert confirm_list(client, preview).status_code == 200
    data = client.get("/api/acompanhamento").json()
    assert data["secoes_esperadas"] == data["secoes_pendentes"] == 5
    assert data["secoes_principais_esperadas"] == data["secoes_principais_pendentes"] == 3
    assert data["secoes_principais_apuradas"] == 0
    assert data["secoes_apuradas"] == data["boletins"] == 0
    assert len(data["grupos_secoes"]) == 3
    assert all(g["status"] == "PENDENTE" for g in data["grupos_secoes"])
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(SecaoEsperada)) == 5


def test_only_actual_coverage_becomes_green_not_expected_aggregates(client, engine, pdf):
    assert confirm_list(client, preview_list(client)).status_code == 200
    seed(engine, pdf, section="1", aggregated=["2"], zone="13")
    data = client.get("/api/acompanhamento").json()
    main = data["grupos_secoes"][0]
    assert main["status"] == "PARCIAL"
    assert main["principal"]["apurada"] is True
    assert [s["apurada"] for s in main["agregadas"]] == [True, False]
    assert main["agregadas"][0]["boletim_id"] == main["principal"]["boletim_id"]
    assert data["secoes_pendentes"] == 3
    assert data["secoes_principais_apuradas"] == 1
    assert data["secoes_principais_pendentes"] == 2
    assert data["grupos_secoes"][2]["principal"]["apurada"] is False  # Other zone.
    seed(engine, pdf, section="0003")
    response = client.get("/api/acompanhamento").json()
    assert response["secoes_principais_apuradas"] == 1
    assert response["secoes_principais_pendentes"] == 2
    updated = response["grupos_secoes"][0]
    assert updated["status"] == "APURADA"
    assert updated["agregadas"][1]["vinculo_divergente"] is True
    assert updated["agregadas"][1]["secao_principal_bu"] == "0003"


def test_import_after_bulletin_and_replacement_preserve_votes(client, engine, pdf):
    seed(engine, pdf, section="0001", aggregated=["0002", "0003"])
    assert confirm_list(client, preview_list(client)).status_code == 200
    before = client.get("/api/acompanhamento").json()
    assert before["grupos_secoes"][0]["status"] == "APURADA"
    assert before["secoes_pendentes"] == 2
    assert before["secoes_principais_esperadas"] == 3
    assert before["secoes_principais_apuradas"] == 1
    assert before["secoes_principais_pendentes"] == 2
    replacement = preview_list(
        client, b"zona;secao_principal;secoes_agregadas\n0013;0001;0002 0003\n"
    )
    assert replacement["substitui_lista"] is True
    assert confirm_list(client, replacement).status_code == 200
    after = client.get("/api/acompanhamento").json()
    assert after["secoes_esperadas"] == 3
    assert after["secoes_pendentes"] == 0
    assert after["secoes_principais_esperadas"] == after["secoes_principais_apuradas"] == 1
    assert after["secoes_principais_pendentes"] == 0
    assert after["cargos"] == before["cargos"]
    assert after["boletins"] == before["boletins"] == 1


def test_principals_without_registry_do_not_invent_expected_totals(client, engine, pdf):
    empty = client.get("/api/acompanhamento").json()
    assert empty["secoes_principais_apuradas"] == 0
    assert empty["secoes_principais_esperadas"] is None
    assert empty["secoes_principais_pendentes"] is None
    seed(engine, pdf, aggregated=["0002", "0003"])
    seed(engine, pdf, section="0004")
    data = client.get("/api/acompanhamento").json()
    assert data["secoes_apuradas"] == 4
    assert data["secoes_principais_apuradas"] == 2
    assert data["secoes_principais_esperadas"] is None
    assert data["secoes_principais_pendentes"] is None


def test_aggregated_only_coverage_does_not_complete_a_principal(client, engine, pdf):
    assert confirm_list(client, preview_list(client)).status_code == 200
    seed(engine, pdf, section="0002")
    data = client.get("/api/acompanhamento").json()
    assert data["grupos_secoes"][0]["status"] == "PARCIAL"
    assert data["secoes_principais_apuradas"] == 0
    assert data["secoes_principais_pendentes"] == 3


def test_principal_imported_as_an_aggregate_remains_pending_in_summary(client, engine, pdf):
    assert confirm_list(client, preview_list(client)).status_code == 200
    seed(engine, pdf, section="0099", aggregated=["0001", "0002", "0003"])
    data = client.get("/api/acompanhamento").json()
    assert data["grupos_secoes"][0]["principal"]["vinculo_divergente"] is True
    assert data["secoes_principais_apuradas"] == 0
    assert data["secoes_principais_pendentes"] == 3


def test_principal_totals_count_isolated_sections_and_exclude_unregistered_bulletins(
    client, engine, pdf
):
    assert confirm_list(client, preview_list(client)).status_code == 200
    seed(engine, pdf, aggregated=["0002", "0003"])
    seed(engine, pdf, section="0004")
    seed(engine, pdf, section="0001", zone="0066")
    seed(engine, pdf, section="0099")
    data = client.get("/api/acompanhamento").json()
    assert data["boletins"] == 4
    assert data["secoes_apuradas"] == 6
    assert data["secoes_principais_esperadas"] == data["secoes_principais_apuradas"] == 3
    assert data["secoes_principais_pendentes"] == 0


def test_stale_and_concurrent_confirmation_are_rejected(client):
    first = preview_list(client)
    second = preview_list(client, b"zona;secao_principal;secoes_agregadas\n0013;0009;\n")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda p: confirm_list(client, p).status_code, [first, second]))
    assert sorted(results) == [200, 409]
    assert client.get("/api/acompanhamento").json()["secoes_esperadas"] in (1, 5)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"zona;secao_principal;secoes_agregadas\n",
        b"zona;secao\n1;2\n",
        b"zona;secao_principal;secoes_agregadas\n1;1;1\n",
        b"zona;secao_principal;secoes_agregadas\n1;1;2\n01;02;\n",
        b"zona;secao_principal;secoes_agregadas\n0;1;\n",
        b"zona;secao_principal;secoes_agregadas\n1;ABC;\n",
        b"zona;secao_principal;secoes_agregadas\n1;1;2;3\n",
        b"zona;secao_principal;secoes_agregadas\n1;1;\xff\n",
    ],
)
def test_invalid_registry_never_changes_existing_list(client, content):
    assert confirm_list(client, preview_list(client)).status_code == 200
    response = client.post(
        "/api/acompanhamento/secoes/preview",
        files={
            "file": ("secoes.csv", content, "text/csv"),
        },
    )
    assert response.status_code == 422
    assert client.get("/api/acompanhamento").json()["secoes_esperadas"] == 5


def test_confirmation_revalidates_duplicates(client):
    preview = preview_list(client)
    preview["grupos"].append(preview["grupos"][0])
    assert confirm_list(client, preview).status_code == 422
    assert client.get("/api/acompanhamento").json()["secoes_esperadas"] is None


def test_csv_formats_bom_and_whitespace():
    content = '\ufeffzona,secao_principal,secoes_agregadas\n 0013 , 0001 ,"0002, 0003"\n\n'
    data = parse_sections_csv(content.encode())
    assert data.grupos[0].zona == "0013"
    assert data.grupos[0].secao_principal == "0001"
    assert data.grupos[0].secoes_agregadas == ["0002", "0003"]


def test_csv_file_type_and_size(client):
    for name, content, status in [("x.pdf", b"PDF", 415), ("x.csv", b"x" * (1024 * 1024 + 1), 413)]:
        assert (
            client.post(
                "/api/acompanhamento/secoes/preview",
                files={
                    "file": (name, content, "text/csv"),
                },
            ).status_code
            == status
        )
