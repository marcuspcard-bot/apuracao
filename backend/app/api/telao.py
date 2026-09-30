import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.telao import (
    AvailableCandidates,
    DivulgacaoResponse,
    TelaoConfigResponse,
    TelaoSave,
)
from app.services.divulgacao_service import divulgacao
from app.services.offices import normalize_office_name
from app.services.telao_service import (
    available_candidates,
    config_response,
    load_config,
    save_config,
)

admin_router = APIRouter(prefix="/api/telao", tags=["Telão"])
public_router = APIRouter(prefix="/api/divulgacao", tags=["Divulgação"])


@admin_router.get("/config", response_model=TelaoConfigResponse)
def get_config(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return config_response(load_config(db))


@admin_router.put("/config", response_model=TelaoConfigResponse)
@admin_router.post("/config", response_model=TelaoConfigResponse)
def update_config(
    body: TelaoSave, request: Request, response: Response, db: Session = Depends(get_db)
):
    result = save_config(db, body)
    request.app.state.screen_events.notify()
    response.headers["Cache-Control"] = "no-store"
    return result


@admin_router.get("/candidatos-disponiveis", response_model=AvailableCandidates)
def candidates(
    response: Response,
    cargo: str = Query(max_length=100),
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
):
    office = normalize_office_name(cargo)
    if office is None:
        raise HTTPException(422, "Cargo desconhecido.")
    response.headers["Cache-Control"] = "no-store"
    return available_candidates(db, office, q, offset, limit)


@public_router.get("", response_model=DivulgacaoResponse)
def results(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return divulgacao(db)


@public_router.get("/eventos")
async def events(request: Request):
    hub = request.app.state.screen_events
    if len(hub.listeners) >= 100:
        raise HTTPException(503, "Atualização por polling disponível.")
    queue = asyncio.Queue(maxsize=1)
    hub.listeners.add(queue)

    async def stream():
        try:
            yield "event: ready\ndata: " + json.dumps({"realtime": hub.connected}) + "\n\n"
            while not await request.is_disconnected():
                try:
                    revision = await asyncio.wait_for(queue.get(), timeout=15)
                    yield "event: update\ndata: " + json.dumps({"revision": revision}) + "\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            hub.listeners.discard(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )
