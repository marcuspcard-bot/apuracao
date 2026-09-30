import json
import logging
from time import monotonic
from uuid import uuid4


logger = logging.getLogger("apuracao.requests")


def configure_request_logging():
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = monotonic()
        status = 500

        async def tracked_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message = {**message, "headers": [*headers, (b"x-request-id", request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        finally:
            if scope["path"] not in ("/health", "/ready") or status >= 400:
                # Never log bodies, query strings, client headers, PDF URLs or credentials.
                route = getattr(scope.get("route"), "path", "unmatched")
                logger.log(
                    logging.ERROR if status >= 500 else logging.INFO,
                    json.dumps(
                        {
                            "event": "http_request",
                            "request_id": request_id,
                            "method": scope["method"],
                            "route": route,
                            "status": status,
                            "duration_ms": round((monotonic() - started) * 1000, 2),
                        }
                    ),
                )
