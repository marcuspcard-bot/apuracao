from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.services.health import database_ready


router = APIRouter(tags=["Health"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/ready")
def ready(available: bool = Depends(database_ready)):
    return JSONResponse(
        {"status": "ok" if available else "unavailable"},
        status_code=200 if available else 503,
        headers={"Cache-Control": "no-store"},
    )
