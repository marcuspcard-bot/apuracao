from functools import lru_cache
from threading import Lock
from time import monotonic

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@lru_cache
def readiness_engine():
    url = make_url(get_settings().database_url)
    if url.drivername in ("postgres", "postgresql"):
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=1000"},
    )


class DatabaseProbe:
    def __init__(self, engine_factory=readiness_engine, ttl=10):
        self.engine_factory = engine_factory
        self.ttl = ttl
        self.lock = Lock()
        self.checked_at = float("-inf")
        self.available = False

    def check(self):
        # Cache both success and failure so public probes cannot exhaust the DB pool.
        with self.lock:
            if monotonic() - self.checked_at < self.ttl:
                return self.available
            try:
                with self.engine_factory().connect() as connection:
                    self.available = connection.scalar(text("SELECT 1")) == 1
            except SQLAlchemyError:
                self.available = False
            self.checked_at = monotonic()
            return self.available


probe = DatabaseProbe()


def database_ready():
    return probe.check()
