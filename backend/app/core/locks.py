import hashlib
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings


def lock_keys(db: Session, keys: Iterable[str]) -> None:
    db.execute(
        text("SELECT set_config('lock_timeout', :timeout, true)"),
        {"timeout": str(get_settings().db_lock_timeout_ms)},
    )
    # All callers use the same order, including overlapping sets of sections.
    for key in sorted(set(keys)):
        lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
