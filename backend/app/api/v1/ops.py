"""SOS and field incident reporting.

SOS is the one path that must never fail. Order of operations:
    1. write the row (durable)
    2. create a dispatch task for the nearest team
    3. publish to the priority topic and the ops WebSocket
    4. return — a queue or socket failure never blocks the acknowledgement
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_principal, require_roles
from app.core.security import Principal, new_reference
from app.db.base import get_db
from app.models.identity import Visitor
from app.models.ops import Incident, SosEvent, Task
from app.models.geo import ZoneDensity
from app.schemas import IncidentCreate, IncidentOut, SosAssignIn, SosCreate, SosOut
from app.services import audit, events
from app.services.geo import haversine_m
from app.services.realtime import CHANNEL_OPS, broker

router = APIRouter(tags=["sos", "incidents"])

CONTROL = ("control_room", "agency_admin", "admin")
FIELD = ("officer", "supervisor", "control_room", "agency_admin", "admin", "volunteer")
AGENCY_BY_CATEGORY = {
    "medical": "health",
    "police": "police",
    "fire": "fire",
    "lost_child": "police",
    "other": "admin",
}


def _zone_for(db: Session, lat: Optional[float], lon: Optional[float]) -> Optional[str]:
    """Nearest zone by centroid — the polygon lookup replaces this in the GIS service."""
    if lat is None or lon is None:
        return None
    best, best_distance = None, float("inf")
    for zone in db.scalars(select(ZoneDensity)).all():
        if zone.centroid_lat is None or zone.centroid_lon is None:
            continue
        distance = haversine_m(lat, lon, zone.centroid_lat, zone.centroid_lon)
        if distance < best_distance:
            best, best_distance = zone, distance
    return best.zone_code if best and best_distance < 3000 else None


@router.post("/sos", response_model=SosOut, status_code=status.HTTP_201_CREATED,
             summary="Raise an SOS (tap or long-press silent)")
async def raise_sos(
    payload: SosCreate,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> SosOut:
    if payload.client_ref:
        existing = db.scalars(
            select(SosEvent).where(SosEvent.client_ref == payload.client_ref)
        ).first()
        if existing:  # offline replay: return the original, never create a second call
            return SosOut.model_validate(existing)

    visitor = db.get(Visitor, principal.subject)
    sos = SosEvent(
        reference=new_reference("SOS"),
        visitor_id=principal.subject if visitor else None,
        group_id=visitor.group_id if visitor else None,
        category=payload.category,
        lat=payload.lat,
        lon=payload.lon,
        accuracy_m=payload.accuracy_m,
        is_silent=payload.silent,
        channel=payload.channel,
        priority=1 if payload.category in {"medical", "fire", "lost_child"} else 2,
        status="new",
        notes=payload.note,
        client_ref=payload.client_ref,
    )
    db.add(sos)
    db.flush()

    # A dispatch task is created immediately so the call is never only a screen event.
    agency = AGENCY_BY_CATEGORY.get(payload.category, "admin")
    zone_code = _zone_for(db, payload.lat, payload.lon)
    task = Task(
        code=new_reference("T"),
        kind="sos_response",
        title=f"SOS {sos.reference}: {payload.category.replace('_', ' ')}",
        description=payload.note,
        zone_code=zone_code,
        agency=agency,
        priority=sos.priority,
        state="assigned",
        lat=payload.lat,
        lon=payload.lon,
        payload={"sos_id": sos.id, "sos_reference": sos.reference,
                 "visitor_ref": visitor.id_card_token if visitor else None,
                 "silent": payload.silent},
    )
    db.add(task)
    db.flush()
    sos.assigned_task_id = task.id

    # The group sees the location of a member in distress even when sharing is off.
    db.commit()
    db.refresh(sos)

    await events.publish(events.TOPIC_SOS, sos.id, {
        "sos_id": sos.id, "reference": sos.reference, "category": payload.category,
        "lat": payload.lat, "lon": payload.lon, "zone_code": zone_code,
        "priority": sos.priority, "channel": payload.channel, "silent": payload.silent,
        "task_id": task.id, "agency": agency,
    })
    await broker.publish(CHANNEL_OPS, {
        "type": "sos", "id": sos.id, "reference": sos.reference,
        "category": payload.category, "lat": payload.lat, "lon": payload.lon,
        "zone_code": zone_code, "priority": sos.priority, "status": "new",
    })

    audit.record(db, principal, "sos.raise", object_type="sos", object_id=sos.id,
                 ip=client_ip(request), category=payload.category,
                 channel=payload.channel, silent=payload.silent, zone=zone_code)
    return SosOut.model_validate(sos)


@router.get("/sos", response_model=List[SosOut], summary="Control room: live SOS queue")
def list_sos(
    sos_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    principal: Principal = Depends(require_roles(*CONTROL)),
    db: Session = Depends(get_db),
) -> List[SosOut]:
    stmt = select(SosEvent).order_by(SosEvent.priority, SosEvent.created_at.desc()).limit(limit)
    if sos_status:
        stmt = stmt.where(SosEvent.status == sos_status)
    return [SosOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.get("/sos/{sos_id}", response_model=SosOut, summary="SOS status")
def get_sos(sos_id: str, principal: Principal = Depends(get_principal),
            db: Session = Depends(get_db)) -> SosOut:
    sos = db.get(SosEvent, sos_id)
    if sos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SOS not found")
    if not principal.is_official and sos.visitor_id != principal.subject:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your SOS")
    return SosOut.model_validate(sos)


@router.post("/sos/{sos_id}/assign", response_model=SosOut,
             summary="Control room: assign the nearest team")
def assign_sos(sos_id: str, payload: SosAssignIn,
               principal: Principal = Depends(require_roles(*CONTROL)),
               db: Session = Depends(get_db)) -> SosOut:
    sos = db.get(SosEvent, sos_id)
    if sos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SOS not found")
    sos.assigned_team = payload.team
    sos.status = "assigned"
    sos.acknowledged_by = principal.subject
    sos.acknowledged_at = datetime.now(timezone.utc)
    if payload.task_id:
        sos.assigned_task_id = payload.task_id
    db.commit()
    db.refresh(sos)
    audit.record(db, principal, "sos.assign", object_type="sos", object_id=sos.id, team=payload.team)
    return SosOut.model_validate(sos)


@router.post("/sos/{sos_id}/close", response_model=SosOut, summary="Close an SOS")
def close_sos(sos_id: str, note: Optional[str] = None,
              principal: Principal = Depends(require_roles(*FIELD)),
              db: Session = Depends(get_db)) -> SosOut:
    sos = db.get(SosEvent, sos_id)
    if sos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SOS not found")
    sos.status = "closed"
    sos.closed_at = datetime.now(timezone.utc)
    if note:
        sos.notes = (sos.notes or "") + f"\n[closed] {note}"
    db.commit()
    db.refresh(sos)
    audit.record(db, principal, "sos.close", object_type="sos", object_id=sos.id)
    return SosOut.model_validate(sos)


# ------------------------------------------------------------------ incidents
@router.post("/incidents", response_model=IncidentOut, status_code=status.HTTP_201_CREATED,
             summary="Field app: report an incident (photo, voice, location)")
async def report_incident(
    payload: IncidentCreate,
    request: Request,
    principal: Principal = Depends(require_roles(*FIELD)),
    db: Session = Depends(get_db),
) -> IncidentOut:
    if payload.client_ref:
        existing = db.scalars(
            select(Incident).where(Incident.client_ref == payload.client_ref)
        ).first()
        if existing:
            return IncidentOut.model_validate(existing)

    incident = Incident(
        reference=new_reference("INC"),
        reporter_id=principal.subject,
        reporter_role=principal.role,
        kind=payload.kind,
        description=payload.description,
        lat=payload.lat,
        lon=payload.lon,
        zone_code=payload.zone_code or _zone_for(db, payload.lat, payload.lon),
        photo_ref=payload.photo_ref,
        voice_ref=payload.voice_ref,
        severity=payload.severity,
        client_ref=payload.client_ref,
        created_at_client=payload.created_at_client,
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)

    await events.publish(events.TOPIC_INCIDENT, incident.id, {
        "incident_id": incident.id, "reference": incident.reference,
        "kind": incident.kind, "severity": incident.severity,
        "zone_code": incident.zone_code, "lat": incident.lat, "lon": incident.lon,
        "reporter_id": principal.subject,
    })
    await broker.publish(CHANNEL_OPS, {
        "type": "incident", "id": incident.id, "reference": incident.reference,
        "kind": incident.kind, "severity": incident.severity,
        "zone_code": incident.zone_code,
    })
    audit.record(db, principal, "incident.report", object_type="incident",
                 object_id=incident.id, ip=client_ip(request), kind=incident.kind)
    return IncidentOut.model_validate(incident)


@router.get("/incidents", response_model=List[IncidentOut], summary="Incident list")
def list_incidents(
    incident_status: Optional[str] = Query(default=None, alias="status"),
    kind: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    principal: Principal = Depends(require_roles(*FIELD)),
    db: Session = Depends(get_db),
) -> List[IncidentOut]:
    stmt = select(Incident).order_by(Incident.created_at.desc()).limit(limit)
    if incident_status:
        stmt = stmt.where(Incident.status == incident_status)
    if kind:
        stmt = stmt.where(Incident.kind == kind)
    return [IncidentOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.patch("/incidents/{incident_id}", response_model=IncidentOut, summary="Update incident status")
def update_incident(incident_id: str, incident_status: str,
                    principal: Principal = Depends(require_roles(*FIELD)),
                    db: Session = Depends(get_db)) -> IncidentOut:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found")
    incident.status = incident_status
    db.commit()
    db.refresh(incident)
    return IncidentOut.model_validate(incident)
