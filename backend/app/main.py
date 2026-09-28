import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.auth import settings_router
from app.api.dashboard import router as dashboard_router
from app.api.email import router as email_router
from app.api.insights import router as insights_router
from app.api.live import router as live_router
from app.api.meetings import router as meetings_router
from app.api.search import router as search_router
from app.api.webhooks import router as webhook_router
from app.auth import ensure_admin
from app.config import get_settings
from app.database import SessionLocal, init_db, ping_db
from app.errors import AppError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    if settings.jwt_secret == "dev-only-change-me-use-a-long-random-secret":
        logger.warning("JWT_SECRET is still the development default")
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)
    delay = 1.0
    for attempt in range(20):
        try:
            await init_db()
            break
        except Exception:
            if attempt == 19:
                raise
            logger.warning("database not ready, retrying")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 5)
    async with SessionLocal() as session:
        await ensure_admin(session)
    stop = asyncio.Event()

    async def _watch() -> None:
        while not stop.is_set():
            try:
                async with SessionLocal() as session:
                    from app.services.watch import scan_calendar

                    await scan_calendar(session)
            except Exception:
                logger.exception("calendar scan failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=max(15, get_settings().calendar_poll_seconds))
            except TimeoutError:
                continue

    watcher = asyncio.create_task(_watch())
    yield
    stop.set()
    watcher.cancel()


app = FastAPI(title="Meeting Intelligence", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error(_, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def unhandled(request, exc: Exception):
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)
    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    try:
        await ping_db()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded"})
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"service": "meeting-intelligence", "docs": "/docs", "health": "/health"}


app.include_router(settings_router)
app.include_router(meetings_router)
app.include_router(email_router)
app.include_router(live_router)
app.include_router(dashboard_router)
app.include_router(search_router)
app.include_router(insights_router)
app.include_router(webhook_router)
