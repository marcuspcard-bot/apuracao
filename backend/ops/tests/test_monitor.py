from datetime import datetime, timezone
import json
from unittest.mock import Mock

import httpx
import pytest

from ops import common, monitor
from ops.common import OpsError


@pytest.mark.parametrize("snapshots,expected", [([], False), ([{"time": "2026-09-30T10:30:00Z"}], True), ([{"time": "2026-09-29T10:00:00Z"}], False), ([{"time": "2026-10-01T10:00:00Z"}], False)])
def test_checks_backup_freshness(monkeypatch, snapshots, expected):
    monkeypatch.setattr(monitor, "restic", lambda *args: json.dumps(snapshots))
    assert monitor.backup_is_recent(datetime(2026, 9, 30, 11, tzinfo=timezone.utc)) is expected


def test_monitor_detects_unprotected_api_database_and_public_bucket(monkeypatch):
    original = httpx.Client

    def api(request):
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/ready":
            return httpx.Response(503, json={"status": "unavailable"})
        return httpx.Response(200, json=[])

    monkeypatch.setattr(monitor.httpx, "Client", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(api)))
    monkeypatch.setattr(monitor, "storage_client", lambda: original(base_url="https://storage.example.test/", transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"public": True}))))
    monkeypatch.setattr(monitor, "backup_is_recent", lambda: False)
    assert monitor.check_services() == {"api": True, "database": False, "operator_access": False, "storage_private": False, "recent_backup": False}


def test_webhook_is_optional_and_sends_only_supplied_status(monkeypatch):
    post = Mock(return_value=Mock(status_code=204))
    monkeypatch.setattr(common.httpx, "post", post)
    assert common.notify_failure("database") is False
    post.assert_not_called()
    monkeypatch.setenv("OPS_ALERT_WEBHOOK_URL", "https://alerts.example.test/private-webhook")
    assert common.notify_failure("database") is True
    assert post.call_args.kwargs["json"] == {"text": "APURACAO: database"}
    assert post.call_args.kwargs["follow_redirects"] is False


def test_no_plain_http_or_embedded_credentials():
    for url in ("http://api.example.test", "https://user:password@api.example.test"):
        with pytest.raises(OpsError):
            common.https_url(url)
