from concurrent.futures import CancelledError, ProcessPoolExecutor, TimeoutError
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import get_context
from threading import BoundedSemaphore, Lock

from app.core.config import get_settings
from app.services.pdf_reader import extract_text_from_pdf


class PdfProcessingError(Exception):
    pass


_lock = Lock()
_executor: ProcessPoolExecutor | None = None
_slots: BoundedSemaphore | None = None


def _get_pool():
    global _executor, _slots
    with _lock:
        if _executor is None:
            settings = get_settings()
            _executor = ProcessPoolExecutor(
                max_workers=settings.pdf_workers, mp_context=get_context("spawn")
            )
            _slots = BoundedSemaphore(settings.pdf_max_pending)
        return _executor, _slots


def shutdown_pdf_pool(failed_pool=None):
    global _executor, _slots
    with _lock:
        if failed_pool is not None and _executor is not failed_pool:
            return
        pool = _executor
        _executor = _slots = None
    if pool is not None:
        pool.shutdown(wait=False, cancel_futures=True)


def read_pdf_text(pdf: bytes) -> str:
    pool, slots = _get_pool()
    if not slots.acquire(blocking=False):
        raise PdfProcessingError("A leitura de PDFs está ocupada. Tente novamente em instantes.")
    try:
        future = pool.submit(extract_text_from_pdf, pdf)
    except (BrokenProcessPool, RuntimeError) as exc:
        slots.release()
        shutdown_pdf_pool(pool)
        raise PdfProcessingError(
            "Não foi possível iniciar a leitura do PDF. Tente novamente."
        ) from exc
    # A timed-out running job still occupies a slot until the worker actually finishes.
    future.add_done_callback(lambda _: slots.release())
    try:
        return future.result(timeout=get_settings().pdf_timeout_seconds)
    except TimeoutError as exc:
        future.cancel()
        raise PdfProcessingError(
            "A leitura do PDF excedeu o tempo limite. Tente novamente."
        ) from exc
    except (BrokenProcessPool, CancelledError) as exc:
        shutdown_pdf_pool(pool)
        raise PdfProcessingError("A leitura do PDF foi interrompida. Tente novamente.") from exc
