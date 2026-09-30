import json
import os
import subprocess
from urllib.parse import urlsplit

import httpx


class OpsError(Exception):
    pass


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise OpsError(f"Configure {name} no ambiente privado de operacoes.")
    return value


def https_url(value):
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise OpsError("Use uma URL HTTPS sem credenciais embutidas.")
    return value.rstrip("/")


def run_tool(args, *, cwd=None, env=None, timeout=900):
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            timeout=timeout,
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OpsError("Ferramenta indisponivel ou tempo limite excedido.") from exc
    if result.returncode:
        # Tool output may contain connection strings. Never emit it to shared logs.
        raise OpsError(f"Operacao interrompida pela ferramenta (codigo {result.returncode}).")
    return result.stdout


def restic(*args, cwd=None):
    required("RESTIC_REPOSITORY")
    if not os.environ.get("RESTIC_PASSWORD_FILE") and len(required("RESTIC_PASSWORD")) < 24:
        raise OpsError("Use uma senha de backup com pelo menos 24 caracteres.")
    return run_tool(["restic", *args], cwd=cwd)


def storage_client():
    key = required("SUPABASE_SERVICE_ROLE_KEY")
    return httpx.Client(
        base_url=https_url(required("SUPABASE_URL")) + "/storage/v1/",
        headers={"apikey": key, "Authorization": "Bearer " + key},
        timeout=httpx.Timeout(45, connect=10),
        follow_redirects=False,
    )


def notify_failure(message):
    url = os.environ.get("OPS_ALERT_WEBHOOK_URL", "")
    if not url:
        return False
    try:
        response = httpx.post(
            https_url(url),
            json={"text": "APURACAO: " + message},
            timeout=10,
            follow_redirects=False,
        )
        return 200 <= response.status_code < 300
    except (httpx.HTTPError, OpsError):
        return False


def report(value):
    print(json.dumps(value, ensure_ascii=True), flush=True)
