import httpx
from fastapi import Request

from app.core.config import get_settings


class StorageError(Exception):
    pass


class StorageService:
    def __init__(self, client: httpx.Client):
        self.settings = get_settings()
        self.client = client

    def request(self, method, path, **kwargs):
        s = self.settings
        if not s.supabase_url or not s.supabase_service_role_key:
            raise StorageError("Storage não configurado.")
        try:
            response = self.client.request(
                method,
                f"{s.supabase_url.rstrip('/')}/storage/v1/{path}",
                headers={
                    "apikey": s.supabase_service_role_key,
                    "Authorization": f"Bearer {s.supabase_service_role_key}",
                    **kwargs.pop("headers", {}),
                },
                **kwargs,
            )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise StorageError("Falha no storage. Tente novamente.") from exc

    def upload(self, bucket: str, path: str, content: bytes):
        try:
            self.request(
                "POST",
                f"object/{bucket}/{path}",
                content=content,
                headers={"Content-Type": "application/pdf", "x-upsert": "false"},
            )
        except StorageError as original:
            # Recover a previous upload whose response or DB transaction was lost.
            # The caller holds the file advisory lock and has checked DB duplicates.
            try:
                existing = self.request("GET", f"object/authenticated/{bucket}/{path}").content
                if existing == content:
                    return
            except StorageError:
                pass
            raise original

    def delete(self, bucket: str, path: str):
        self.request("DELETE", f"object/{bucket}", json={"prefixes": [path]})

    def signed_url(self, bucket: str, path: str) -> str:
        result = self.request("POST", f"object/sign/{bucket}/{path}", json={"expiresIn": 60}).json()
        return f"{self.settings.supabase_url.rstrip('/')}/storage/v1{result['signedURL']}"


def create_storage_client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        timeout=httpx.Timeout(settings.storage_timeout_seconds, connect=10, pool=5),
        limits=httpx.Limits(
            max_connections=settings.storage_max_connections,
            max_keepalive_connections=settings.storage_max_connections,
            keepalive_expiry=30,
        ),
    )


def get_storage(request: Request) -> StorageService:
    return request.app.state.storage
