import base64
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TelaoCandidato
from app.services import candidate_photos
from tests.test_acompanhamento import cargo, seed
from tests.test_telao import configuration, save, screen


def photo(color="red", file_format="PNG"):
    output = BytesIO()
    Image.new("RGB", (200, 300), color).save(output, file_format)
    mime = {"PNG": "png", "JPEG": "jpeg", "WEBP": "webp"}[file_format]
    return f"data:image/{mime};base64," + base64.b64encode(output.getvalue()).decode()


def selection(foto):
    return {"cargo": "GOVERNADOR", "numero": "40", "ativo": True, "foto": foto}


@pytest.mark.parametrize("file_format", ["PNG", "JPEG", "WEBP"])
def test_photo_is_normalized_without_metadata(file_format):
    result = candidate_photos.prepare_photo(photo(file_format=file_format))
    with Image.open(BytesIO(result)) as image:
        assert image.format == "WEBP" and image.size == (512, 512)
        assert not image.getexif()


@pytest.mark.parametrize(
    "invalid",
    [
        "data:image/svg+xml;base64,PHN2Zz4=",
        "https://example.test/image.png",
        "data:image/png;base64,not-base64",
        "data:image/png;base64,SGVsbG8=",
        "data:image/png;base64,",
        "data:text/html;base64,PGgxPnRlc3Q8L2gxPg==",
    ],
)
def test_photo_rejects_invalid_or_active_content(invalid):
    with pytest.raises(HTTPException) as error:
        candidate_photos.prepare_photo(invalid)
    assert error.value.status_code == 422


def test_photo_limits_size_dimensions_and_mime(monkeypatch):
    with pytest.raises(HTTPException):
        candidate_photos.prepare_photo(photo().replace("image/png", "image/jpeg"))
    monkeypatch.setattr(candidate_photos, "MAX_PHOTO_PIXELS", 100)
    with pytest.raises(HTTPException):
        candidate_photos.prepare_photo(photo())
    monkeypatch.setattr(candidate_photos, "MAX_PHOTO_BYTES", 1)
    with pytest.raises(HTTPException):
        candidate_photos.prepare_photo(photo())


def test_photo_upload_display_replace_remove_and_preserve_votes(client, engine, pdf, storage):
    seed(engine, pdf, cargos=[cargo("GOVERNADOR", "40", 123)])
    saved = save(client, [], candidatos=[selection(photo())])
    assert saved.status_code == 200, saved.text
    candidate = saved.json()["candidatos"][0]
    url = candidate["foto_url"]
    assert url == screen(client)["candidatos"][0]["foto_url"]
    assert len(storage.objects) == 1
    assert next(iter(storage.objects))[0] == "candidatos"
    response = client.get(url)
    assert response.status_code == 200 and response.headers["content-type"] == "image/webp"
    assert client.get(url, headers={"If-None-Match": response.headers["etag"]}).status_code == 304
    assert client.get(url.split("?")[0] + "?v=obsolete").status_code == 404
    assert save(client, [("GOVERNADOR", "40")]).json()["candidatos"][0]["foto_url"] == url
    replaced = save(client, [], candidatos=[selection(photo("blue"))]).json()["candidatos"][0]
    assert replaced["id"] == candidate["id"] and replaced["foto_url"] != url
    assert len(storage.objects) == 1 and client.get(url).status_code == 404
    assert screen(client)["candidatos"][0]["votos"] == 123
    assert save(client, [], candidatos=[selection(None)]).status_code == 200
    assert screen(client)["candidatos"][0]["foto_url"] is None
    assert storage.objects == {}


def test_photo_scope_reorder_candidate_removal_and_bulletin_cleanup(client, engine, pdf, storage):
    from sqlalchemy import delete
    from app.models import Boletim

    seed(engine, pdf, cargos=[cargo("GOVERNADOR", "40"), cargo("PRESIDENTE", "40")])
    items = [selection(photo()), {**selection(photo("blue")), "cargo": "PRESIDENTE"}]
    assert save(client, [], candidatos=items).status_code == 200
    urls = {c["cargo"]: c["foto_url"] for c in screen(client)["candidatos"]}
    assert len(set(urls.values())) == 2
    assert save(client, [("PRESIDENTE", "40"), ("GOVERNADOR", "40")]).status_code == 200
    assert {c["cargo"]: c["foto_url"] for c in screen(client)["candidatos"]} == urls
    with engine.begin() as connection:
        connection.execute(delete(Boletim))
    assert all(
        c["foto_url"] == urls[c["cargo"]] and c["votos"] == 0 for c in screen(client)["candidatos"]
    )
    assert save(client, [("PRESIDENTE", "40")]).status_code == 200
    assert len(storage.objects) == 1
    assert client.get(urls["GOVERNADOR"]).status_code == 404


def test_photo_failure_and_stale_config_keep_previous_photo(client, engine, pdf, storage):
    seed(engine, pdf, cargos=[cargo("GOVERNADOR", "40")])
    assert save(client, [], candidatos=[selection(photo())]).status_code == 200
    before = configuration(client)
    original = dict(storage.objects)
    assert save(client, [], version=0, candidatos=[selection(photo("blue"))]).status_code == 409
    assert storage.objects == original
    storage.fail = True
    assert save(client, [], candidatos=[selection(photo("blue"))]).status_code == 502
    assert configuration(client) == before and storage.objects == original
    storage.fail = False
    assert (
        save(client, [], candidatos=[selection("data:image/png;base64,bm90LWltYWdl")]).status_code
        == 422
    )
    assert configuration(client) == before and storage.objects == original


def test_partial_photo_upload_is_cleaned_when_later_photo_is_invalid(client, engine, pdf, storage):
    seed(engine, pdf, cargos=[cargo("GOVERNADOR", "40"), cargo("PRESIDENTE", "40")])
    items = [selection(photo()), {**selection("invalid"), "cargo": "PRESIDENTE"}]
    assert save(client, [], candidatos=items).status_code == 422
    assert storage.objects == {} and configuration(client)["versao"] == 0


def test_ambiguous_commit_never_deletes_referenced_photo(client, engine, pdf, storage):
    seed(engine, pdf, cargos=[cargo("GOVERNADOR", "40")])
    assert save(client, [], candidatos=[selection(photo())]).status_code == 200
    with Session(engine) as db:
        candidate = db.scalar(select(TelaoCandidato))
        reference = (candidate.foto_bucket, candidate.foto_path)
        candidate_photos.discard_uncommitted_photos(db, storage, [reference])
    assert reference in storage.objects


def test_simultaneous_photo_changes_keep_only_the_committed_image(client, engine, pdf, storage):
    seed(engine, pdf, cargos=[cargo("GOVERNADOR", "40")])
    assert save(client, [], candidatos=[selection(photo())]).status_code == 200
    version = configuration(client)["versao"]

    def replace(color):
        return save(client, [], version=version, candidatos=[selection(photo(color))]).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(replace, ["blue", "green"])) == [200, 409]
    assert configuration(client)["versao"] == version + 1
    assert len(storage.objects) == 1
    assert client.get(screen(client)["candidatos"][0]["foto_url"]).status_code == 200
