import asyncio

import pytest
from starlette.responses import JSONResponse

from app.core.config import get_settings
from app.core.request_limits import BodyLimitMiddleware, ImportCapacityMiddleware


async def exchange(app, *, path="/api/boletins/preview", method="POST", headers=(), receive=None):
    messages = []

    async def default_receive():
        return {"type": "http.request", "body": b"{}"}

    async def send(message):
        messages.append(message)

    await app(
        {"type": "http", "path": path, "method": method, "headers": list(headers)},
        receive or default_receive,
        send,
    )
    return messages


async def success(scope, receive, send):
    if scope["method"] == "POST":
        await receive()
    await JSONResponse({"ok": True})(scope, receive, send)


def status(messages):
    return next(
        message["status"] for message in messages if message["type"] == "http.response.start"
    )


def test_capacity_rejects_sixth_import_before_reading_and_keeps_reads_available():
    async def run():
        ready, release = asyncio.Event(), asyncio.Event()
        active = 0

        async def blocked(scope, receive, send):
            nonlocal active
            if scope["method"] == "POST":
                active += 1
                if active == 5:
                    ready.set()
                await release.wait()
            await success(scope, receive, send)

        app = ImportCapacityMiddleware(blocked)
        tasks = [asyncio.create_task(exchange(app)) for _ in range(5)]
        try:
            await asyncio.wait_for(ready.wait(), 2)

            async def unread():
                raise AssertionError("Rejected requests must not buffer the PDF")

            rejected = await exchange(app, path="/api/boletins/confirmar/", receive=unread)
            assert status(rejected) == 503
            assert (b"retry-after", b"2") in rejected[0]["headers"]
            assert status(await exchange(app, path="/api/divulgacao", method="GET")) == 200
        finally:
            release.set()
            responses = await asyncio.gather(*tasks)
        assert [status(r) for r in responses] == [200] * 5
        assert status(await exchange(app)) == 200

    asyncio.run(run())


@pytest.mark.parametrize("declared,expected", [(b"2000000", 413), (b"-1", 400), (b"invalid", 400)])
def test_bad_declared_size_is_rejected_before_reading(monkeypatch, declared, expected):
    monkeypatch.setattr(get_settings(), "max_pdf_size_mb", 1)

    async def unread():
        raise AssertionError("Unexpected body read")

    messages = asyncio.run(
        exchange(
            BodyLimitMiddleware(success), headers=[(b"content-length", declared)], receive=unread
        )
    )
    assert status(messages) == expected


def test_chunked_body_is_bounded_without_content_length(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_pdf_size_mb", 1)
    chunks = [b"a" * (1024 * 1024), b"b" * (1024 * 1024)]

    async def receive():
        return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}

    assert status(asyncio.run(exchange(BodyLimitMiddleware(success), receive=receive))) == 413


def test_multipart_and_confirmation_have_different_size_budgets(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_pdf_size_mb", 1)

    async def receive():
        return {"type": "http.request", "body": b"a" * 1500000}

    app = BodyLimitMiddleware(success)
    assert status(asyncio.run(exchange(app, receive=receive))) == 413
    assert (
        status(asyncio.run(exchange(app, path="/api/boletins/confirmar/", receive=receive))) == 200
    )


def test_slow_body_releases_import_capacity(monkeypatch):
    monkeypatch.setattr(get_settings(), "request_body_timeout_seconds", 0.01)
    monkeypatch.setattr(get_settings(), "import_max_concurrent", 1)

    async def run():
        async def stalled():
            await asyncio.Event().wait()

        app = ImportCapacityMiddleware(BodyLimitMiddleware(success))
        assert status(await exchange(app, receive=stalled)) == 408
        assert status(await exchange(app)) == 200

    asyncio.run(run())


def test_screen_photo_configuration_has_its_own_bounded_body_budget(monkeypatch):
    monkeypatch.setattr(get_settings(), "max_pdf_size_mb", 1)
    app = BodyLimitMiddleware(success)

    async def receive():
        return {"type": "http.request", "body": b"a" * 3000000}

    assert status(asyncio.run(exchange(app, path="/api/telao/config", receive=receive))) == 200

    async def unread():
        raise AssertionError("Oversized photos must be rejected before reading")

    messages = asyncio.run(
        exchange(
            app,
            path="/api/telao/config",
            method="PUT",
            receive=unread,
            headers=[(b"content-length", b"20971521")],
        )
    )
    assert status(messages) == 413


@pytest.mark.parametrize("failure", ["disconnect", "exception", "cancel"])
def test_interrupted_upload_always_releases_capacity(monkeypatch, failure):
    monkeypatch.setattr(get_settings(), "import_max_concurrent", 1)

    async def run():
        started = asyncio.Event()

        async def interrupted():
            started.set()
            if failure == "disconnect":
                return {"type": "http.disconnect"}
            if failure == "exception":
                raise RuntimeError("simulated transport error")
            await asyncio.Event().wait()

        app = ImportCapacityMiddleware(BodyLimitMiddleware(success))
        if failure == "disconnect":
            assert await exchange(app, receive=interrupted) == []
        elif failure == "exception":
            with pytest.raises(RuntimeError):
                await exchange(app, receive=interrupted)
        else:
            task = asyncio.create_task(exchange(app, receive=interrupted))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert status(await exchange(app)) == 200

    asyncio.run(run())
