"""Liveness and readiness probes, plus the build stamp clients can read."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import SUPPORTED_LANGUAGES, settings
from app.db.base import get_db

router = APIRouter(tags=["health"])

BUILD_STAMP = "0.1.0"
BUILD_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@router.get("/healthz", summary="Liveness")
def healthz() -> dict:
    return {"status": "ok", "build": BUILD_STAMP}


@router.get("/readyz", summary="Readiness: database reachable")
def readyz(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "up"}


@router.get("/version", summary="Build stamp and enabled integrations")
def version() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.version,
        "build": BUILD_STAMP,
        "built_at": BUILD_TIME,
        "env": settings.env,
        "languages": SUPPORTED_LANGUAGES,
        "integrations": {
            "kafka": bool(settings.kafka_bootstrap),
            "sms_gateway": bool(settings.sms_gateway_url),
            "push": bool(settings.push_key),
            "weather": bool(settings.weather_api_url),
            "routing_engine": bool(settings.routing_engine_url),
        },
    }
