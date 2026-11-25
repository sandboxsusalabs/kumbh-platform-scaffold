"""FastAPI application entry point.

Run locally:      uvicorn app.main:app --reload --port 8000
Docs:             http://localhost:8000/docs
Visitor app:      http://localhost:8000/app/
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from app.api.v1 import api_router
from app.api.v1 import health
from app.api.v1.health import BUILD_STAMP
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("kumbh")


def _log_database_state() -> None:
    """Log the selected database without credentials and flag unapplied migrations."""
    database_url = make_url(settings.database_url)
    log.info("database url=%s", database_url.render_as_string(hide_password=True))
    try:
        from app.db.base import engine

        scripts = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic"))
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
        head = set(scripts.get_heads())
        if current != head:
            log.warning("Alembic is not at head: current=%s head=%s",
                        sorted(current) or "unversioned", sorted(head))
    except Exception as exc:  # noqa: BLE001
        log.warning("could not verify Alembic head for configured database: %s", exc)


def _frontend_dir() -> Path | None:
    """The visitor app shell, served from the same origin as the API."""
    candidates = [
        Path(__file__).resolve().parents[2] / "frontend" / "visitor-app",  # repo layout
        Path("/srv-frontend/visitor-app"),                                 # container layout
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    _log_database_state()
    if settings.is_dev:
        from app.db.base import create_all

        create_all()
        log.warning("dev mode: schema created directly, use Alembic outside dev")
    log.info("kumbh api %s up env=%s kafka=%s", BUILD_STAMP, settings.env,
             bool(settings.kafka_bootstrap))
    yield
    log.info("kumbh api shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "One shared backend for the Haridwar Kumbh Mela platform: the multilingual "
        "visitor app, the agency command dashboard and the field operations app."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=800)

app.include_router(api_router)
app.include_router(health.router)  # probes live at the root, outside /v1


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace to a phone on a weak network; log it server-side."""
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error"})


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/app/")


frontend = _frontend_dir()
if frontend is not None:
    app.mount("/app", StaticFiles(directory=str(frontend), html=True), name="visitor-app")
else:  # pragma: no cover - only when the shell is not shipped alongside the API
    log.warning("visitor app shell not found; /app will 404")
