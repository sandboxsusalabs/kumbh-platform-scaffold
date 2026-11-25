"""Crowd density, bathing schedule and weather.

The density indicator is the app's most-read widget on a peak day, so it is served from
a small table updated by the telemetry worker rather than computed per request.
"""
from __future__ import annotations

from datetime import date as date_type
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import Principal
from app.db.base import get_db
from app.models.geo import SnanSlot, WeatherSnapshot, ZoneDensity
from app.schemas import CrowdIngestIn, SnanSlotOut, WeatherOut, ZoneOut
from app.services import events
from app.services.geo import level_for_ratio
from app.services.realtime import CHANNEL_OPS, broker

router = APIRouter(tags=["crowd"])

CONTROL = ("control_room", "agency_admin", "admin")


@router.get("/crowd/zones", response_model=List[ZoneOut], summary="Green/amber/red by zone")
def zones(
    level: Optional[str] = Query(default=None, pattern="^(green|amber|red)$"),
    ghats_only: bool = False,
    db: Session = Depends(get_db),
) -> List[ZoneOut]:
    stmt = select(ZoneDensity).order_by(ZoneDensity.occupancy_ratio.desc())
    if level:
        stmt = stmt.where(ZoneDensity.level == level)
    if ghats_only:
        stmt = stmt.where(ZoneDensity.is_ghat.is_(True))
    return [ZoneOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.get("/crowd/ghats", response_model=List[ZoneOut], summary="Bathing ghats with live density")
def ghats(db: Session = Depends(get_db)) -> List[ZoneOut]:
    stmt = select(ZoneDensity).where(ZoneDensity.is_ghat.is_(True))
    return [ZoneOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.post("/crowd/ingest", response_model=ZoneOut,
             summary="Internal: push a CCTV / gate-counter / network reading")
async def ingest(
    payload: CrowdIngestIn,
    principal: Principal = Depends(require_roles(*CONTROL)),
    db: Session = Depends(get_db),
) -> ZoneOut:
    zone = db.get(ZoneDensity, payload.zone_code)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown zone")

    zone.estimated_persons = payload.estimated_persons
    zone.inflow_per_min = payload.inflow_per_min
    zone.outflow_per_min = payload.outflow_per_min
    zone.source = payload.source
    if payload.one_way_flow is not None:
        zone.one_way_flow = payload.one_way_flow
    if payload.is_closed is not None:
        zone.is_closed = payload.is_closed
    zone.occupancy_ratio = (
        payload.estimated_persons / zone.capacity if zone.capacity else 0.0
    )
    zone.level = level_for_ratio(zone.occupancy_ratio)
    db.commit()
    db.refresh(zone)

    await events.publish(events.TOPIC_CROWD, zone.zone_code, {
        "zone_code": zone.zone_code, "level": zone.level,
        "occupancy_ratio": zone.occupancy_ratio, "is_closed": zone.is_closed,
    })
    await broker.publish(CHANNEL_OPS, {
        "type": "zone_density", "zone_code": zone.zone_code,
        "level": zone.level, "occupancy_ratio": round(zone.occupancy_ratio, 3),
    })
    return ZoneOut.model_validate(zone)


@router.get("/schedule/snan", response_model=List[SnanSlotOut],
            summary="Today's bathing schedule by ghat (shahi snan flagged)")
def snan_schedule(
    on: Optional[date_type] = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
) -> List[SnanSlotOut]:
    stmt = select(SnanSlot).order_by(SnanSlot.date, SnanSlot.start_time)
    if on:
        stmt = stmt.where(SnanSlot.date == on)
    return [SnanSlotOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.get("/weather", response_model=WeatherOut, summary="Temperature, rain and river-level warning")
def weather(db: Session = Depends(get_db)) -> WeatherOut:
    stmt = select(WeatherSnapshot).order_by(WeatherSnapshot.recorded_at.desc()).limit(1)
    snapshot = db.scalars(stmt).first()
    if snapshot is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no weather reading yet")
    return WeatherOut.model_validate(snapshot)
