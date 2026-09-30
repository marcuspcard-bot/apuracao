import hashlib
import json
import os
import shutil
from uuid import uuid4

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest

from ops import backup
from ops.common import OpsError, restic, run_tool


PDF = b"%PDF-1.7\nsynthetic backup fixture\n%%EOF"
ROW = {"id": "09d07cdb-5b68-43da-b3f0-54de3527f5ab", "storage_bucket": "boletins", "storage_path": "2026/test.pdf", "arquivo_hash": hashlib.sha256(PDF).hexdigest()}


def fake_storage(*, content=PDF, public=False, missing=False):
    def handle(request):
        if "/bucket/" in request.url.path:
            return httpx.Response(200, json={"id": "boletins", "public": public})
        return httpx.Response(404 if missing else 200, content=content)
    return httpx.Client(base_url="https://storage.example.test/storage/v1/", transport=httpx.MockTransport(handle))


def test_download_preserves_exact_bytes_and_source_paths(tmp_path):
    with fake_storage() as client:
        objects, buckets = backup.download_objects(client, [ROW], tmp_path)
    assert (tmp_path / objects[0]["file"]).read_bytes() == PDF
    assert objects[0]["path"] == ROW["storage_path"]
    assert objects[0]["sha256"] == ROW["arquivo_hash"]
    assert buckets["boletins"]["public"] is False


@pytest.mark.parametrize("options", [{"content": b"corrupted"}, {"public": True}, {"missing": True}])
def test_incomplete_or_public_storage_aborts_backup(tmp_path, options):
    with fake_storage(**options) as client:
        with pytest.raises((OpsError, httpx.HTTPError)):
            backup.download_objects(client, [ROW], tmp_path)


@pytest.mark.parametrize("path", ["../file.pdf", "a/../file.pdf", "/file.pdf", "a\\file.pdf"])
def test_rejects_unsafe_source_paths(tmp_path, path):
    with fake_storage() as client:
        with pytest.raises(OpsError):
            backup.download_objects(client, [{**ROW, "storage_path": path}], tmp_path)


def test_does_not_publish_a_partial_backup(monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "restic", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(backup, "export_database", lambda *args, **kwargs: ([ROW], {}, "test"))
    monkeypatch.setattr(backup, "storage_client", lambda: fake_storage(content=b"wrong"))
    with pytest.raises(OpsError):
        backup.create_backup()
    assert calls == [("cat", "config")]


def test_verifier_rejects_modified_data_and_traversal(tmp_path):
    target = tmp_path / "database.dump"
    target.write_bytes(b"test dump")
    manifest = {"format": 1, "database": {"file": "database.dump", "sha256": backup.file_hash(target)}, "objects": [], "table_counts": {"boletins": 0}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    assert backup.verify_backup(tmp_path)["arquivos_verificados"] == 1
    target.write_bytes(b"modified")
    with pytest.raises(OpsError):
        backup.verify_backup(tmp_path)
    manifest["database"]["file"] = "../outside.dump"
    path.write_text(json.dumps(manifest))
    with pytest.raises(OpsError):
        backup.verify_backup(tmp_path)


def test_connection_parser_preserves_encoded_password(monkeypatch):
    monkeypatch.setenv("BACKUP_DATABASE_URL", "postgresql+psycopg://reader:p%40ss%25word@db.example.test:5432/postgres?sslmode=require")
    params = backup.connection_parameters()
    assert params["password"] == "p@ss%word"
    assert params["sslmode"] == "require"


def test_encrypted_backup_and_database_restore_with_concurrent_insert(tmp_path, monkeypatch):
    if not all(shutil.which(tool) for tool in ("pg_dump", "pg_restore", "restic")):
        pytest.skip("Integration runs in Dockerfile.ops test target, with PostgreSQL and restic tools.")
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("Set TEST_DATABASE_URL to the isolated local PostgreSQL.")
    params = conninfo_to_dict(value.replace("postgresql+psycopg://", "postgresql://", 1))
    assert params.get("host") in ("localhost", "127.0.0.1", "::1")
    assert params.get("dbname") == "apuracao" and params.get("port") == "55432"
    monkeypatch.setenv("BACKUP_DATABASE_URL", value)
    schema = "ops_test_" + uuid4().hex
    restored_db = "ops_restore_" + uuid4().hex
    with psycopg.connect(**params, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored_db)))
        try:
            admin.execute(sql.SQL("CREATE TABLE {}.boletins (id uuid PRIMARY KEY, storage_bucket text, storage_path text, arquivo_hash text)").format(sql.Identifier(schema)))
            insert = sql.SQL("INSERT INTO {}.boletins VALUES (%s, %s, %s, %s)").format(sql.Identifier(schema))
            admin.execute(insert, tuple(ROW[key] for key in ("id", "storage_bucket", "storage_path", "arquivo_hash")))
            original_tool = backup.run_tool

            def dump_after_new_upload(args, **kwargs):
                admin.execute(insert, (uuid4(), "boletins", "later.pdf", "0" * 64))
                assert "password" not in " ".join(args).lower()
                return original_tool(args, **kwargs)

            monkeypatch.setattr(backup, "run_tool", dump_after_new_upload)
            monkeypatch.setattr(backup, "storage_client", fake_storage)
            restic("init")
            result = backup.create_backup(schema=schema)
            assert result["pdfs"] == 1
            destination = tmp_path / "restored"
            restic("restore", result["snapshot"], "--target", str(destination))
            manifests = list(destination.rglob("manifest.json"))
            assert len(manifests) == 1
            root = manifests[0].parent
            assert backup.verify_backup(root)["table_counts"]["boletins"] == 1
            assert (root / "pdfs" / (ROW["id"] + ".pdf")).read_bytes() == PDF
            env = {**os.environ, "PGHOST": params["host"], "PGPORT": params["port"], "PGUSER": params["user"], "PGPASSWORD": params["password"]}
            run_tool(["pg_restore", "--no-owner", "--no-acl", "--exit-on-error", "--dbname=" + restored_db, str(root / "database.dump")], env=env)
            with psycopg.connect(**{**params, "dbname": restored_db}) as restored:
                count = restored.execute(sql.SQL("SELECT count(*) FROM {}.boletins").format(sql.Identifier(schema))).fetchone()[0]
                assert count == 1
                value = restored.execute(sql.SQL("SELECT arquivo_hash FROM {}.boletins").format(sql.Identifier(schema))).fetchone()[0]
                assert value == ROW["arquivo_hash"]
            monkeypatch.setenv("RESTIC_PASSWORD", "incorrect-password-still-long-enough")
            with pytest.raises(OpsError):
                restic("cat", "config")
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(restored_db)))
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
