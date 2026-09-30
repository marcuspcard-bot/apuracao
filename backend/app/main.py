import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.boletins import router
from app.api.acompanhamento import router as acompanhamento_router
from app.api.telao import admin_router as telao_router, public_router as divulgacao_router
from app.core.config import get_settings
from app.core.request_limits import BodyLimitMiddleware, ImportCapacityMiddleware
from app.services.pdf_processing import shutdown_pdf_pool
from app.services.storage_service import StorageService, create_storage_client
from app.services.telao_realtime import ScreenEvents


@asynccontextmanager
async def lifespan(app):
    with create_storage_client() as storage_client:
        app.state.storage = StorageService(storage_client)
        app.state.screen_events = ScreenEvents()
        await app.state.screen_events.start()
        try:
            yield
        finally:
            await app.state.screen_events.stop()
            shutdown_pdf_pool()


app = FastAPI(title="Importação de Boletins de Urna", version="1.0.0", lifespan=lifespan)
app.include_router(router)
app.include_router(acompanhamento_router)
app.include_router(telao_router)
app.include_router(divulgacao_router)


app.add_middleware(BodyLimitMiddleware)
app.add_middleware(ImportCapacityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        {"detail": "Requisição inválida. Confira o arquivo ou envie uma nova prévia."},
        status_code=422,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logging.getLogger(__name__).exception("Falha no banco", exc_info=exc)
    return JSONResponse({"detail": "Falha no banco de dados. Tente novamente."}, status_code=503)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logging.getLogger(__name__).exception("Erro interno", exc_info=exc)
    return JSONResponse(
        {"detail": "Não foi possível concluir a operação. Tente novamente."},
        status_code=500,
    )


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
