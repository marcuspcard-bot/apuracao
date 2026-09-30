import configparser
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import quote
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from ops.common import OpsError, required, restic, run_tool, storage_client


TAG = "apuracao"


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connection_parameters():
    value = required("BACKUP_DATABASE_URL")
    if value.startswith("postgresql+psycopg://"):
        value = "postgresql://" + value.removeprefix("postgresql+psycopg://")
    params = conninfo_to_dict(value)
    if "service" in params or any("\n" in str(v) or "\r" in str(v) for v in params.values()):
        raise OpsError("Use uma URI PostgreSQL completa para o backup.")
    params["connect_timeout"] = "10"
    return params


def export_database(directory, *, schema="public"):
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", schema):
        raise OpsError("Nome de schema invalido.")
    params = connection_parameters()
    # A private libpq service file keeps the database password out of process arguments.
    with TemporaryDirectory(prefix="apuracao-pg-") as private:
        service = Path(private) / "pg_service.conf"
        config = configparser.ConfigParser(interpolation=None)
        config["backup"] = params
        with service.open("w", encoding="utf-8") as target:
            config.write(target)
        service.chmod(0o600)
        env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
        env.update(PGSERVICEFILE=str(service), PGSERVICE="backup")
        with psycopg.connect(**params, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL statement_timeout = '120s'")
            connection.execute("SET LOCAL idle_in_transaction_session_timeout = '15min'")
            snapshot = connection.execute("SELECT pg_export_snapshot() AS id").fetchone()["id"]
            started_at = connection.execute("SELECT now() AS value").fetchone()["value"].isoformat()
            rows = connection.execute(
                sql.SQL(
                    "SELECT id::text, storage_bucket, storage_path, arquivo_hash FROM {}.boletins ORDER BY id"
                ).format(sql.Identifier(schema))
            ).fetchall()
            counts = {}
            tables = connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
                (schema,),
            ).fetchall()
            for table in tables:
                name = table["table_name"]
                counts[name] = connection.execute(
                    sql.SQL("SELECT count(*) AS total FROM {}.{}").format(
                        sql.Identifier(schema),
                        sql.Identifier(name),
                    )
                ).fetchone()["total"]
            run_tool(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--schema=" + schema,
                    "--snapshot=" + snapshot,
                    "--lock-wait-timeout=10s",
                    "--file=" + str(directory / "database.dump"),
                ],
                env=env,
            )
    return rows, counts, started_at


def private_bucket(client, bucket):
    if not bucket or any(char in bucket for char in ("/", "\\")) or bucket in (".", ".."):
        raise OpsError("Nome de bucket invalido.")
    response = client.get("bucket/" + quote(bucket, safe=""))
    response.raise_for_status()
    metadata = response.json()
    if metadata.get("public") is not False or metadata.get("id") != bucket:
        raise OpsError("O bucket de boletins deve existir e permanecer privado.")
    return metadata


def download_objects(client, rows, directory):
    pdfs = directory / "pdfs"
    pdfs.mkdir()
    objects = []
    primary = required("SUPABASE_STORAGE_BUCKET")
    buckets = {primary: private_bucket(client, primary)}
    for row in rows:
        bucket, path = row["storage_bucket"], row["storage_path"]
        if (
            not bucket
            or "/" in bucket
            or "\\" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
        ):
            raise OpsError("Caminho de PDF invalido no banco.")
        if bucket not in buckets:
            buckets[bucket] = private_bucket(client, bucket)
        filename = str(UUID(row["id"])) + ".pdf"
        target = pdfs / filename
        with client.stream(
            "GET", "object/authenticated/" + quote(bucket, safe="") + "/" + quote(path, safe="/")
        ) as response:
            response.raise_for_status()
            with target.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    output.write(chunk)
        digest = file_hash(target)
        if digest != row["arquivo_hash"]:
            raise OpsError("PDF com hash divergente. Backup nao foi publicado.")
        objects.append(
            {
                "boletim_id": row["id"],
                "bucket": bucket,
                "path": path,
                "file": "pdfs/" + filename,
                "sha256": digest,
                "bytes": target.stat().st_size,
            }
        )
    return objects, buckets


def create_backup(*, schema="public"):
    # Fail before exporting data if the encrypted destination has not been initialized.
    restic("cat", "config")
    with TemporaryDirectory(prefix="apuracao-backup-") as private:
        directory = Path(private)
        rows, counts, started_at = export_database(directory, schema=schema)
        with storage_client() as client:
            objects, buckets = download_objects(client, rows, directory)
        manifest = {
            "format": 1,
            "snapshot_at": started_at,
            "schema": schema,
            "database": {"file": "database.dump", "sha256": file_hash(directory / "database.dump")},
            "table_counts": counts,
            "objects": objects,
            "buckets": buckets,
        }
        (directory / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8"
        )
        output = restic(
            "backup",
            "--json",
            "--tag",
            TAG,
            "--host",
            "apuracao",
            "--",
            "database.dump",
            "manifest.json",
            "pdfs",
            cwd=directory,
        )
        summaries = [json.loads(line) for line in output.splitlines() if line.strip()]
        snapshot = next(
            (row.get("snapshot_id") for row in summaries if row.get("message_type") == "summary"),
            None,
        )
        if not snapshot:
            raise OpsError("Nao foi possivel confirmar o snapshot criptografado.")
        return {
            "status": "ok",
            "snapshot": snapshot,
            "pdfs": len(objects),
            "snapshot_at": started_at,
        }


def verify_backup(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1:
        raise OpsError("Formato de backup desconhecido.")
    items = [manifest["database"], *manifest["objects"]]
    for item in items:
        target = (directory / item["file"]).resolve()
        if (
            not target.is_relative_to(directory)
            or not target.is_file()
            or file_hash(target) != item["sha256"]
        ):
            raise OpsError("Arquivo ausente ou divergente no backup restaurado.")
    return {
        "status": "ok",
        "arquivos_verificados": len(items),
        "table_counts": manifest["table_counts"],
    }
