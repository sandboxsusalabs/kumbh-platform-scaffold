"""Administration: audit log, analytics summary, officer accounts."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import Principal
from app.db.base import get_db
from app.models.comms import Alert, AuditLog
from app.models.geo import ZoneDensity
from app.models.identity import Officer, Visitor
from app.models.ops import Feedback, Incident, LostPersonCase, SosEvent, Task
from app.schemas import AnalyticsSummary
from app.services import audit

router = APIRouter(prefix="/admin", tags=["administration"])

ADMINS = ("agency_admin", "admin")
CONTROL = ("control_room", "agency_admin", "admin")


def _count(db: Session, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    for condition in conditions:
        stmt = stmt.where(condition)
    return int(db.scalar(stmt) or 0)


@router.get("/audit-logs", summary="Who viewed or changed what (append-only)")
def audit_logs(
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    principal: Principal = Depends(require_roles(*ADMINS)),
    db: Session = Depends(get_db),
) -> List[dict]:
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": row.id, "actor_id": row.actor_id, "actor_role": row.actor_role,
            "agency": row.agency, "action": row.action, "object_type": row.object_type,
            "object_id": row.object_id, "ip": row.ip, "meta": row.meta,
            "at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/analytics/summary", response_model=AnalyticsSummary,
            summary="Daily operations numbers for the review meeting")
def analytics(principal: Principal = Depends(require_roles(*CONTROL)),
              db: Session = Depends(get_db)) -> AnalyticsSummary:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    open_sos_states = ["new", "assigned", "en_route", "on_site"]
    sos_rows = db.scalars(select(SosEvent).where(SosEvent.created_at >= since)).all()
    ack_seconds = [
        (row.acknowledged_at.replace(tzinfo=timezone.utc) - row.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        for row in sos_rows
        if row.acknowledged_at and row.created_at
    ]

    zones = db.scalars(select(ZoneDensity)).all()
    return AnalyticsSummary(
        generated_at=now,
        registered_visitors=_count(db, Visitor, Visitor.is_active.is_(True), Visitor.name.is_not(None)),
        active_sos=_count(db, SosEvent, SosEvent.status.in_(open_sos_states)),
        open_incidents=_count(db, Incident, Incident.status != "closed"),
        open_lost_cases=_count(db, LostPersonCase, LostPersonCase.status.in_(["open", "sighting", "matched"])),
        open_tasks=_count(db, Task, Task.state.notin_(["done", "cancelled"])),
        open_complaints=_count(db, Feedback, Feedback.status != "resolved"),
        zones_red=sum(1 for z in zones if z.level == "red"),
        zones_amber=sum(1 for z in zones if z.level == "amber"),
        median_sos_ack_seconds=round(statistics.median(ack_seconds), 1) if ack_seconds else None,
        alerts_last_24h=_count(db, Alert, Alert.created_at >= since),
    )


@router.get("/officers", summary="Staff accounts and their agency/zone scope")
def officers(principal: Principal = Depends(require_roles(*ADMINS)),
             db: Session = Depends(get_db)) -> List[dict]:
    rows = db.scalars(select(Officer).order_by(Officer.agency, Officer.name)).all()
    return [
        {"id": o.id, "employee_code": o.employee_code, "name": o.name, "role": o.role,
         "agency": o.agency, "zone": o.zone, "is_active": o.is_active,
         "mfa_enabled": bool(o.totp_secret)}
        for o in rows
    ]


@router.post("/officers/{officer_id}/deactivate", summary="Disable an account immediately")
def deactivate(officer_id: str, principal: Principal = Depends(require_roles(*ADMINS)),
               db: Session = Depends(get_db)) -> dict:
    officer = db.get(Officer, officer_id)
    if officer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "officer not found")
    officer.is_active = False
    db.commit()
    audit.record(db, principal, "officer.deactivate", object_type="officer", object_id=officer_id)
    return {"id": officer_id, "is_active": False}
