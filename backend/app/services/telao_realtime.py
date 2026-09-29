import asyncio
import logging
from contextlib import suppress

from realtime import AsyncRealtimeClient
from realtime.types import RealtimeSubscribeStates

from app.core.config import get_settings
from app.services.acompanhamento import ELEICAO_DATA, MUNICIPIO_CODIGO, TURNO
from app.services.telao_service import ZONA

logger = logging.getLogger(__name__)
WATCHED_TABLES = ("boletins", "secoes_esperadas", "telao_config", "telao_candidatos")


class ScreenEvents:
    """Relay invalidations, never electoral rows or Supabase credentials, to public clients."""

    def __init__(self):
        self.connected = False
        self.revision = 0
        self.listeners: set[asyncio.Queue] = set()
        self.loop = None
        self.task = None

    async def start(self):
        self.loop = asyncio.get_running_loop()
        settings = get_settings()
        if (
            settings.telao_realtime_enabled
            and settings.supabase_url
            and settings.supabase_service_role_key
        ):
            self.task = asyncio.create_task(self._run())

    async def stop(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        self.connected = False
        self.loop = None

    def notify(self):
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._publish)

    def _publish(self):
        self.revision += 1
        for queue in tuple(self.listeners):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(self.revision)

    def on_change(self, payload):
        data = payload.get("data", {})
        table = data.get("table")
        if table not in WATCHED_TABLES:
            return
        record = data.get("record") or data.get("old_record") or {}
        if table in ("boletins", "secoes_esperadas") and record.get("municipio_codigo") is not None:
            try:
                if (
                    int(record["municipio_codigo"]) != int(MUNICIPIO_CODIGO)
                    or int(record.get("zona", record.get("zona_chave", 0))) != int(ZONA)
                    or str(record.get("eleicao_data")) != ELEICAO_DATA.isoformat()
                    or int(record.get("eleicao_turno", 0)) != TURNO
                ):
                    return
            except (ValueError, TypeError):
                return
        self.notify()

    async def _run(self):
        settings = get_settings()
        while True:
            client = AsyncRealtimeClient(
                settings.supabase_url.rstrip("/") + "/realtime/v1",
                settings.supabase_service_role_key,
                auto_reconnect=False,
                max_retries=1,
                timeout=10,
            )
            stopped = asyncio.Event()

            def status_changed(status, error):
                self.connected = status == RealtimeSubscribeStates.SUBSCRIBED
                if self.connected:
                    self.notify()
                else:
                    stopped.set()

            try:
                await asyncio.wait_for(client.connect(), timeout=15)
                channel = client.channel("telao-server")
                for table in WATCHED_TABLES:
                    channel.on_postgres_changes(
                        "*", schema="public", table=table, callback=self.on_change
                    )
                await channel.subscribe(status_changed)
                while not stopped.is_set():
                    await asyncio.sleep(5)
                    if not client.is_connected:
                        break
            except asyncio.CancelledError:
                raise
            except Exception:
                # Do not log URLs/exceptions from the SDK: its websocket URL contains a credential.
                logger.warning("Realtime indisponível; divulgação continua por polling.")
            finally:
                self.connected = False
                with suppress(Exception):
                    await asyncio.wait_for(client.close(), timeout=5)
            await asyncio.sleep(10)
