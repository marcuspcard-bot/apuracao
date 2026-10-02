import httpx
from fastapi import Request

from app.core.config import get_settings


class StorageError(Exception):
    def __init__(self, message, status_code=None, code=None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


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
        except httpx.HTTPStatusError as exc:
            try:
                details = exc.response.json()
            except ValueError:
                details = {}
            code = details.get("code") if isinstance(details, dict) else None
            raise StorageError(
                "Falha no storage. Tente novamente.", exc.response.status_code, code
            ) from exc
        except httpx.HTTPError as exc:
            raise StorageError("Falha no storage. Tente novamente.") from exc

    def upload(self, bucket: str, path: str, content: bytes, content_type="application/pdf"):
        try:
            self.request(
                "POST",
                f"object/{bucket}/{path}",
                content=content,
                headers={"Content-Type": content_type, "x-upsert": "false"},
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

    def download(self, bucket: str, path: str) -> bytes:
        return self.request("GET", f"object/authenticated/{bucket}/{path}").content

    def ensure_photo_bucket(self, bucket: str):
        try:
            details = self.request("GET", f"bucket/{bucket}").json()
        except StorageError as exc:
            # Storage can return HTTP 400 with a more precise error code in its JSON body.
            if exc.status_code != 404 and exc.code != "NoSuchBucket":
                raise
            try:
                self.request(
                    "POST",
                    "bucket",
                    json={
                        "id": bucket,
                        "name": bucket,
                        "public": False,
                        "allowed_mime_types": ["image/webp"],
                        "file_size_limit": 2 * 1024 * 1024,
                    },
                )
            except StorageError as create_error:
                if create_error.status_code != 409 and create_error.code != "BucketAlreadyExists":
                    raise
            details = self.request("GET", f"bucket/{bucket}").json()
        if details.get("public") is not False:
            raise StorageError("O bucket de fotos deve ser privado.")

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
