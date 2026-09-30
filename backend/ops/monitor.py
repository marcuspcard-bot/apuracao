from datetime import datetime, timezone
import json
import os

import httpx

from ops.backup import TAG
from ops.common import OpsError, https_url, required, restic, storage_client


def backup_is_recent(now=None):
    now = now or datetime.now(timezone.utc)
    maximum = float(os.environ.get("BACKUP_MAX_AGE_HOURS", "3"))
    if not 0 < maximum <= 168:
        raise OpsError("BACKUP_MAX_AGE_HOURS deve estar entre 0 e 168.")
    snapshots = json.loads(restic("snapshots", "--json", "--tag", TAG, "--host", "apuracao"))
    dates = [datetime.fromisoformat(row["time"].replace("Z", "+00:00")) for row in snapshots]
    if not dates:
        return False
    age = (now - max(dates)).total_seconds()
    return -300 <= age <= maximum * 3600


def check_services():
    checks = {}
    base = https_url(required("PUBLIC_API_URL"))
    with httpx.Client(base_url=base, timeout=10, follow_redirects=False) as client:
        for name, path in (("api", "/health"), ("database", "/ready")):
            try:
                response = client.get(path)
                checks[name] = response.status_code == 200 and response.json().get("status") == "ok"
            except (httpx.HTTPError, ValueError):
                checks[name] = False
        try:
            # No secret is sent: the public origin must deny operator endpoints.
            checks["operator_access"] = (
                client.get("/api/boletins", params={"limit": 1}).status_code == 403
            )
        except httpx.HTTPError:
            checks["operator_access"] = False
    try:
        with storage_client() as client:
            bucket = required("SUPABASE_STORAGE_BUCKET")
            if "/" in bucket:
                raise OpsError("Bucket invalido.")
            response = client.get("bucket/" + bucket)
            checks["storage_private"] = (
                response.status_code == 200 and response.json().get("public") is False
            )
    except (httpx.HTTPError, ValueError, OpsError):
        checks["storage_private"] = False
    try:
        checks["recent_backup"] = backup_is_recent()
    except (OpsError, ValueError, KeyError, TypeError):
        checks["recent_backup"] = False
    return checks
