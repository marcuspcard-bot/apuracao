import pytest


@pytest.fixture(autouse=True)
def isolated_operations_environment(monkeypatch, tmp_path):
    for name in ("BACKUP_DATABASE_URL", "RESTIC_PASSWORD_FILE", "OPS_ALERT_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://storage.example.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-storage-secret")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "boletins")
    monkeypatch.setenv("RESTIC_REPOSITORY", str(tmp_path / "repository"))
    monkeypatch.setenv("RESTIC_PASSWORD", "test-backup-password-not-for-production")
    monkeypatch.setenv("PUBLIC_API_URL", "https://api.example.test")
    monkeypatch.setenv("BACKUP_MAX_AGE_HOURS", "1")
