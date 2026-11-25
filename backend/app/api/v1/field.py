"""Field operations app: task inbox, state transitions, offline sync.

The field app queues actions locally and replays them through `/field/sync`. Every item
carries a `client_ref`, so a replay after a dropped connection can never create a second
incident or a second SOS.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.security import Principal
from app.db.base import get_db
from app.models.geo import Facility
from app.models.ops import Incident, SosEvent, Task, TaskEvent
from app.schemas import SyncIn, SyncItemResult, SyncOut, TaskOut, TaskTransitionIn
from app.services import audit
from app.services.geo import haversine_m
from app.services.realtime import CHANNEL_OPS, broker

router = APIRouter(prefix="/field", tags=["field app"])

FIELD = ("officer", "supervisor", "control_room", "agency_admin", "admin", "volunteer")
ALLOWED_TRANSITIONS = {
    "assigned": {"accepted", "cancelled"},
    "accepted": {"en_route", "cancelled"},
    "en_route": {"on_site", "cancelled"},
    "on_site": {"done", "cancelled"},
    "done": set(),
    "cancelled": set(),
}


def _apply_transition(db: Session, task: Task, payload: TaskTransitionIn,
                      principal: Principal) -> Task:
    if payload.state not in ALLOWED_TRANSITIONS.get(task.state, set()):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot move task from '{task.state}' to '{payload.state}'",
        )
    task.state = payload.state
    if payload.state == "done":
        task.completed_at = datetime.now(timezone.utc)
    db.add(TaskEvent(
        task_id=task.id,
        state=payload.state,
        actor_id=principal.subject,
        lat=payload.lat,
        lon=payload.lon,
        photo_ref=payload.photo_ref,
        note=payload.note,
    ))
    return task


@router.get("/tasks", response_model=List[TaskOut],
            summary="My task inbox, nearest first")
def my_tasks(
    task_state: Optional[str] = Query(default=None, alias="state"),
    include_unassigned: bool = False,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    principal: Principal = Depends(require_roles(*FIELD)),
    db: Session = Depends(get_db),
) -> List[TaskOut]:
    stmt = select(Task)
    if include_unassigned:
        stmt = stmt.where(
            (Task.assignee_id == principal.subject) | (Task.assignee_id.is_(None))
        )
    else:
        stmt = stmt.where(Task.assignee_id == principal.subject)
    if task_state:
        stmt = stmt.where(Task.state == task_state)
    stmt = stmt.order_by(Task.priority, Task.created_at.desc())

    tasks = list(db.scalars(stmt).all())
    if lat is not None and lon is not None:
        tasks.sort(key=lambda t: haversine_m(lat, lon, t.lat, t.lon)
                   if t.lat is not None and t.lon is not None else float("inf"))
    return [TaskOut.model_validate(task) for task in tasks]


@router.post("/tasks/{task_id}/claim", response_model=TaskOut,
             summary="Claim an unassigned task (nearest available responder)")
async def claim(task_id: str, principal: Principal = Depends(require_roles(*FIELD)),
                db: Session = Depends(get_db)) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    if task.assignee_id and task.assignee_id != principal.subject:
        raise HTTPException(status.HTTP_409_CONFLICT, "task already claimed")
    task.assignee_id = principal.subject
    task.state = "accepted"
    db.add(TaskEvent(task_id=task.id, state="accepted", actor_id=principal.subject))
    db.commit()
    db.refresh(task)
    await broker.publish(CHANNEL_OPS, {"type": "task_claimed", "task_id": task.id,
                                      "by": principal.subject})
    return TaskOut.model_validate(task)


@router.post("/tasks/{task_id}/transition", response_model=TaskOut,
             summary="Accept / en-route / on-site / done, with geotagged proof")
async def transition(task_id: str, payload: TaskTransitionIn,
                     principal: Principal = Depends(require_roles(*FIELD)),
                     db: Session = Depends(get_db)) -> TaskOut:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
    if task.assignee_id not in (None, principal.subject):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "task belongs to another officer")

    task.assignee_id = task.assignee_id or principal.subject
    _apply_transition(db, task, payload, principal)
    db.commit()
    db.refresh(task)

    await broker.publish(CHANNEL_OPS, {"type": "task_state", "task_id": task.id,
                                      "state": task.state, "by": principal.subject})
    audit.record(db, principal, "task.transition", object_type="task", object_id=task.id,
                 state=payload.state, photo=bool(payload.photo_ref))
    return TaskOut.model_validate(task)


@router.post("/sync", response_model=SyncOut,
             summary="Replay queued offline actions (idempotent by client_ref)")
async def sync(payload: SyncIn, principal: Principal = Depends(require_roles(*FIELD)),
               db: Session = Depends(get_db)) -> SyncOut:
    results: List[SyncItemResult] = []

    for item in payload.items:
        try:
            if item.kind == "incident":
                existing = db.scalars(
                    select(Incident).where(Incident.client_ref == item.client_ref)
                ).first()
                if existing:
                    results.append(SyncItemResult(client_ref=item.client_ref,
                                                  status="duplicate", server_id=existing.id))
                    continue
                data = item.payload
                incident = Incident(
                    reference="INC-SYNC-" + item.client_ref[-6:].upper(),
                    reporter_id=principal.subject,
                    reporter_role=principal.role,
                    kind=data.get("kind", "other"),
                    description=data.get("description"),
                    lat=data.get("lat"),
                    lon=data.get("lon"),
                    zone_code=data.get("zone_code"),
                    photo_ref=data.get("photo_ref"),
                    voice_ref=data.get("voice_ref"),
                    severity=data.get("severity", "medium"),
                    client_ref=item.client_ref,
                )
                db.add(incident)
                db.commit()
                results.append(SyncItemResult(client_ref=item.client_ref, status="applied",
                                              server_id=incident.id))

            elif item.kind == "facility_status":
                facility = db.get(Facility, item.payload.get("facility_id", ""))
                if facility is None:
                    results.append(SyncItemResult(client_ref=item.client_ref, status="rejected",
                                                  reason="unknown facility"))
                    continue
                facility.status = item.payload.get("status", facility.status)
                facility.updated_by = principal.subject
                db.commit()
                await broker.publish(CHANNEL_OPS, {"type": "facility_status",
                                                  "facility_id": facility.id,
                                                  "status": facility.status})
                results.append(SyncItemResult(client_ref=item.client_ref, status="applied",
                                              server_id=facility.id))

            elif item.kind == "task_transition":
                task = db.get(Task, item.payload.get("task_id", ""))
                if task is None:
                    results.append(SyncItemResult(client_ref=item.client_ref, status="rejected",
                                                  reason="unknown task"))
                    continue
                already = db.scalars(
                    select(TaskEvent).where(TaskEvent.task_id == task.id,
                                            TaskEvent.state == item.payload.get("state"))
                ).first()
                if already:
                    results.append(SyncItemResult(client_ref=item.client_ref, status="duplicate",
                                                  server_id=task.id))
                    continue
                _apply_transition(db, task, TaskTransitionIn(**{
                    k: item.payload.get(k) for k in ("state", "lat", "lon", "photo_ref", "note")
                    if item.payload.get(k) is not None
                }), principal)
                db.commit()
                results.append(SyncItemResult(client_ref=item.client_ref, status="applied",
                                              server_id=task.id))

            elif item.kind == "sos":
                existing = db.scalars(
                    select(SosEvent).where(SosEvent.client_ref == item.client_ref)
                ).first()
                results.append(SyncItemResult(
                    client_ref=item.client_ref,
                    status="duplicate" if existing else "rejected",
                    server_id=existing.id if existing else None,
                    reason=None if existing else "SOS must go through /sos for priority handling",
                ))
            else:
                results.append(SyncItemResult(client_ref=item.client_ref, status="rejected",
                                              reason="unsupported kind"))
        except HTTPException as exc:
            db.rollback()
            results.append(SyncItemResult(client_ref=item.client_ref, status="rejected",
                                          reason=str(exc.detail)))
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            results.append(SyncItemResult(client_ref=item.client_ref, status="rejected",
                                          reason=f"server error: {type(exc).__name__}"))

    return SyncOut(results=results, server_time=datetime.now(timezone.utc))
