from functools import lru_cache
import re
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "boletins"
    frontend_url: str = "http://localhost:5173"
    operator_frontend_url: str = ""
    max_pdf_size_mb: int = Field(default=10, ge=1, le=50)
    preview_secret_key: str
    preview_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    db_pool_size: int = Field(default=5, ge=1, le=20)
    db_max_overflow: int = Field(default=5, ge=0, le=20)
    db_pool_timeout_seconds: int = Field(default=10, ge=1, le=60)
    db_connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    db_lock_timeout_ms: int = Field(default=10000, ge=100, le=60000)
    pdf_workers: int = Field(default=2, ge=1, le=4)
    pdf_max_pending: int = Field(default=10, ge=5, le=20)
    pdf_timeout_seconds: int = Field(default=30, ge=1, le=120)
    import_max_concurrent: int = Field(default=5, ge=1, le=20)
    request_body_timeout_seconds: int = Field(default=120, ge=10, le=300)
    storage_max_connections: int = Field(default=10, ge=5, le=50)
    storage_timeout_seconds: int = Field(default=45, ge=5, le=120)
    telao_realtime_enabled: bool = True
    operator_access_mode: Literal["open", "proxy"] = "open"
    operator_proxy_key: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def valid_operator_access(self):
        if self.operator_access_mode == "proxy" and not re.fullmatch(
            r"[A-Za-z0-9_-]{43,128}", self.operator_proxy_key.get_secret_value()
        ):
            raise ValueError(
                "OPERATOR_PROXY_KEY deve conter uma chave aleatoria de 43 a 128 caracteres."
            )
        return self

    @field_validator("preview_secret_key")
    @classmethod
    def valid_key(cls, value):
        Fernet(value.encode())
        return value

    @field_validator("frontend_url")
    @classmethod
    def valid_origin(cls, value):
        if value == "*" or not value.startswith(("http://", "https://")):
            raise ValueError("FRONTEND_URL deve ser uma origem HTTP explicita.")
        return value.rstrip("/")

    @field_validator("operator_frontend_url")
    @classmethod
    def valid_operator_origin(cls, value):
        return cls.valid_origin(value) if value else ""


@lru_cache
def get_settings():
    return Settings()
