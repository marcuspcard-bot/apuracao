from threading import BoundedSemaphore

import anyio
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.config import get_settings


class ImportCapacityMiddleware:
    """Bound the complete import, including body reception and Storage, per API process."""

    def __init__(self, app):
        self.app = app
        self.slots = BoundedSemaphore(get_settings().import_max_concurrent)

    async def __call__(self, scope, receive, send):
        is_import = (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"].rstrip("/")
            in (
                "/api/boletins/preview",
                "/api/boletins/confirmar",
                "/api/boletins/manual/confirmar",
                "/api/boletins/fotos/preview",
                "/api/boletins/fotos/ler",
            )
        )
        if not is_import:
            return await self.app(scope, receive, send)
        if not self.slots.acquire(blocking=False):
            response = JSONResponse(
                {
                    "detail": "Há importações em processamento. Aguarde alguns segundos e tente novamente."
                },
                status_code=503,
                headers={"Retry-After": "2"},
            )
            return await response(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            self.slots.release()


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT"):
            return await self.app(scope, receive, send)
        settings = get_settings()
        limit = settings.max_pdf_size_mb * 1024 * 1024
        # The preview token contains base64 PDF inside Fernet; multipart needs overhead.
        limit = (
            limit * 2 + 8192
            if scope["path"].rstrip("/").endswith(("/confirmar", "/fotos/ler"))
            else limit + 65536
        )
        if scope["path"].rstrip("/") == "/api/telao/config":
            limit = 20 * 1024 * 1024
        length = Headers(scope=scope).get("content-length")
        if length is not None:
            try:
                declared = int(length)
                if declared < 0:
                    raise ValueError
            except ValueError:
                return await JSONResponse(
                    {"detail": "Tamanho da requisição inválido."}, status_code=400
                )(scope, receive, send)
            if declared > limit:
                return await self.too_large(scope, receive, send)

        chunks, size = [], 0
        try:
            with anyio.fail_after(settings.request_body_timeout_seconds):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    size += len(message.get("body", b""))
                    if size > limit:
                        return await self.too_large(scope, receive, send)
                    chunks.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        break
        except TimeoutError:
            return await JSONResponse(
                {
                    "detail": "O envio excedeu o tempo limite. Confira sua conexão e tente novamente."
                },
                status_code=408,
            )(scope, receive, send)

        async def replay():
            if chunks:
                body = b"".join(chunks)
                chunks.clear()
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def too_large(scope, receive, send):
        return await JSONResponse(
            {"detail": "O arquivo excede o tamanho máximo permitido."}, status_code=413
        )(scope, receive, send)
