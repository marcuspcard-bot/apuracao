import hmac

from starlette.responses import JSONResponse

from app.core.config import get_settings


PROXY_HEADER = b"x-operator-proxy-key"
PUBLIC_PATHS = frozenset({"/health", "/ready", "/api/divulgacao", "/api/divulgacao/eventos"})


class OperatorAccessMiddleware:
    """The private gateway authenticates devices; its secret never reaches browsers."""

    def __init__(self, app):
        self.app = app
        settings = get_settings()
        self.protected = settings.operator_access_mode == "proxy"
        self.key = settings.operator_proxy_key.get_secret_value().encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])
        supplied = [value for name, value in headers if name.lower() == PROXY_HEADER]
        scope["headers"] = [
            (name, value) for name, value in headers if name.lower() != PROXY_HEADER
        ]
        public = scope["method"] in ("GET", "HEAD") and scope["path"].rstrip("/") in PUBLIC_PATHS
        if self.protected and not public:
            authorized = len(supplied) == 1 and hmac.compare_digest(supplied[0], self.key)
            if not authorized:
                return await JSONResponse(
                    {
                        "detail": "Acesso restrito aos computadores autorizados. Conecte a rede privada."
                    },
                    status_code=403,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
        await self.app(scope, receive, send)
