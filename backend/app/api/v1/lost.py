"""Lost-person cases: registration, registry, sightings, reunion.

One registry serves all three apps — the family reports in the visitor app, the desk
works the case in the dashboard, and field staff register a found person in desk mode.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_roles
from app.core.security import Principal, TokenError, decode_token, new_reference
from app.db.base import get_db
from app.models.identity import Group, GroupMember, Visitor
from app.models.ops import LostPersonCase, LostPersonSighting, Task
from app.schemas import LostPersonCreate, LostPersonOut, SightingIn
from app.services import audit
from app.services.geo import nearest_facilities
from app.services.realtime import CHANNEL_OPS, broker

router = APIRouter(prefix="/lost-persons", tags=["lost and found"])
optional_bearer = HTTPBearer(auto_error=False)

CONTROL = ("control_room", "agency_admin", "admin")
FIELD = ("officer", "supervisor", "control_room", "agency_admin", "admin", "volunteer")
REPORT_DESK = ("officer", "supervisor", "control_room", "agency_admin", "admin")
DESK_STATUSES = {"Reported": "open", "Under Search": "sighting", "Found": "matched", "Reunited": "reunited"}


@router.post("", response_model=LostPersonOut, status_code=status.HTTP_201_CREATED,
             summary="Report a missing person (photo, description, last-seen location)")
async def report(
    payload: LostPersonCreate,
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
) -> LostPersonOut:
    principal = None
    if credentials:
        try:
            principal = decode_token(credentials.credentials)
        except TokenError:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
        if principal.role != "visitor":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "visitor token required")
        visitor = db.get(Visitor, principal.subject)
        if visitor is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "visitor account was not found")
    elif not all((payload.reporter_name, payload.reporter_phone, payload.reporter_relation,
                  payload.subject_age is not None, payload.subject_gender, payload.last_seen_place,
                  payload.last_seen_at)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "complete report and reporter details are required")

    last_seen_at = payload.last_seen_at or datetime.now(timezone.utc)
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    if last_seen_at > datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "last seen time cannot be in the future")
    if payload.photo_ref and (len(payload.photo_ref) > 7_000_000 or not re.match(r"^data:image/(jpeg|png);base64,", payload.photo_ref)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "photo must be a JPG or PNG up to 5 MB")

    centre_id = None
    if payload.last_seen_lat is not None and payload.last_seen_lon is not None:
        nearest = nearest_facilities(db, lat=payload.last_seen_lat, lon=payload.last_seen_lon,
                                     radius_m=50_000, category="lost_found", only_open=True, limit=1)
        if nearest:
            centre_id = nearest[0][0].id
    case_no = f"LP-{datetime.now(timezone.utc).year}-{secrets.token_hex(4).upper()}"
    case = LostPersonCase(
        case_no=case_no,
        reported_by_visitor_id=principal.subject if principal else None,
        group_member_id=payload.group_member_id,
        subject_name=payload.subject_name,
        subject_age=payload.subject_age,
        subject_gender=payload.subject_gender,
        description=payload.description,
        photo_ref=payload.photo_ref,
        languages_spoken=payload.languages_spoken,
        medical_needs=payload.medical_needs,
        reporter_name=payload.reporter_name,
        reporter_phone=payload.reporter_phone,
        reporter_relation=payload.reporter_relation,
        alternate_phone=payload.alternate_phone,
        reporter_location=payload.reporter_location,
        last_seen_lat=payload.last_seen_lat,
        last_seen_lon=payload.last_seen_lon,
        last_seen_place=payload.last_seen_place,
        last_seen_at=last_seen_at,
        centre_id=centre_id,
        is_child=payload.is_child or (payload.subject_age is not None and payload.subject_age < 18),
        status="open",
    )
    db.add(case)
    db.flush()

    # Photo circulation to nearby staff is a task, not a broadcast to every phone.
    db.add(Task(
        code=new_reference("T"),
        kind="lost_person",
        title=f"Lost person: {case.subject_name} ({case.case_no})",
        description=payload.description,
        zone_code=None,
        agency="police",
        priority=1,
        lat=payload.last_seen_lat,
        lon=payload.last_seen_lon,
        payload={"case_id": case.id, "case_no": case.case_no, "photo_ref": payload.photo_ref,
                 "centre_id": case.centre_id},
    ))
    db.commit()
    db.refresh(case)

    await broker.publish(CHANNEL_OPS, {
        "type": "lost_person", "id": case.id, "case_no": case.case_no,
        "is_child": case.is_child, "status": "open", "centre_id": case.centre_id,
    })
    audit.record(db, principal, "lost_person.report", object_type="lost_person_case",
                 object_id=case.id, ip=client_ip(request), is_child=case.is_child)
    return LostPersonOut.model_validate(case)


@router.get("/track", summary="Track a case using the case number and reporter phone")
def track_case(
    request: Request,
    case_no: str = Query(min_length=8, max_length=24),
    phone: str = Query(pattern=r"^[6-9][0-9]{9}$"),
    db: Session = Depends(get_db),
) -> dict:
    case = db.scalars(select(LostPersonCase).where(
        LostPersonCase.case_no == case_no.strip().upper(),
        LostPersonCase.reporter_phone == phone,
    )).first()
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case or reporter phone was not found")
    statuses = {"open": "Reported", "sighting": "Under Search", "matched": "Found",
                "reunited": "Reunited", "closed": "Reunited"}
    audit.record(db, None, "lost_person.track", object_type="lost_person_case", object_id=case.id,
                 ip=client_ip(request) if request else None)
    return {"case_no": case.case_no, "subject_name": case.subject_name,
            "status": statuses.get(case.status, "Reported"),
            "last_seen_place": case.last_seen_place, "created_at": case.created_at}


@router.get("", summary="Paginated missing-person reports")
def list_cases(
    case_status: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = Query(default=None, max_length=120),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(LostPersonCase)
    if case_status:
        status_value = DESK_STATUSES.get(case_status, case_status)
        if status_value not in DESK_STATUSES.values():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid status")
        stmt = stmt.where(LostPersonCase.status == status_value)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(LostPersonCase.case_no.ilike(term),
                              LostPersonCase.subject_name.ilike(term)))
    if date_from:
        stmt = stmt.where(LostPersonCase.created_at >= date_from)
    if date_to:
        if date_to.hour == 0 and date_to.minute == 0 and date_to.second == 0:
            date_to = date_to + timedelta(days=1, microseconds=-1)
        stmt = stmt.where(LostPersonCase.created_at <= date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(LostPersonCase.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    result = {"items": [LostPersonOut.model_validate(row).model_dump(exclude={"photo_ref"}) | {
                "subject_gender": row.subject_gender, "last_seen_at": row.last_seen_at,
                "last_seen_lat": row.last_seen_lat, "last_seen_lon": row.last_seen_lon,
            } for row in rows], "page": page, "page_size": page_size, "total": total}
    audit.record(db, None, "lost_person.list", object_type="lost_person_case")
    return result


@router.get("/{case_id}", summary="Public missing-person report details")
def get_case(case_id: str, db: Session = Depends(get_db)) -> dict:
    case = db.get(LostPersonCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")

    sightings = db.scalars(
        select(LostPersonSighting).where(LostPersonSighting.case_id == case_id)
        .order_by(LostPersonSighting.created_at.desc())
    ).all()

    data = LostPersonOut.model_validate(case).model_dump()
    data.update({"subject_gender": case.subject_gender, "photo_ref": case.photo_ref,
                 "last_seen_lat": case.last_seen_lat, "last_seen_lon": case.last_seen_lon,
                 "last_seen_at": case.last_seen_at, "languages_spoken": case.languages_spoken,
                 "medical_needs": case.medical_needs})
    data["sightings"] = [
        {"lat": s.lat, "lon": s.lon, "note": s.note, "at": s.created_at.isoformat()}
        for s in sightings
    ]
    audit.record(db, None, "lost_person.detail", object_type="lost_person_case", object_id=case.id)
    return data


@router.patch("/{case_id}/status", summary="Update case status (staff desk)")
def update_status(case_id: str, payload: dict, request: Request,
                  principal: Principal = Depends(require_roles(*REPORT_DESK)),
                  db: Session = Depends(get_db)) -> dict:
    requested = payload.get("status") if isinstance(payload, dict) else None
    if requested not in DESK_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid status")
    case = db.get(LostPersonCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
    case.status = DESK_STATUSES[requested]
    case.status_changed_by = principal.subject
    case.status_changed_at = datetime.now(timezone.utc)
    if case.status == "reunited":
        case.reunited_at = case.status_changed_at
    db.commit()
    db.refresh(case)
    audit.record(db, principal, "lost_person.status_update", object_type="lost_person_case",
                 object_id=case.id, ip=client_ip(request), status=requested)
    return {"id": case.id, "case_no": case.case_no, "status": requested,
            "status_changed_by": case.status_changed_by,
            "status_changed_at": case.status_changed_at.isoformat()}


@router.post("/{case_id}/sighting", response_model=LostPersonOut,
             summary="Field app: log a sighting or a found person match")
async def sighting(case_id: str, payload: SightingIn,
                   principal: Principal = Depends(require_roles(*FIELD)),
                   db: Session = Depends(get_db)) -> LostPersonOut:
    case = db.get(LostPersonCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")

    db.add(LostPersonSighting(
        case_id=case_id,
        reported_by=principal.subject,
        lat=payload.lat,
        lon=payload.lon,
        note=payload.note,
    ))
    if case.status == "open":
        case.status = "sighting"
    db.commit()
    db.refresh(case)

    await broker.publish(CHANNEL_OPS, {"type": "lost_person_sighting", "id": case.id,
                                      "case_no": case.case_no})
    audit.record(db, principal, "lost_person.sighting", object_type="lost_person_case",
                 object_id=case_id)
    return LostPersonOut.model_validate(case)


@router.post("/{case_id}/found", response_model=LostPersonOut,
             summary="Confirm that the missing person has been found")
async def mark_found(case_id: str, request: Request,
                     principal: Principal = Depends(require_roles(*FIELD)),
                     db: Session = Depends(get_db)) -> LostPersonOut:
    case = db.get(LostPersonCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")
    case.status = "matched"
    db.commit()
    db.refresh(case)
    await broker.publish(CHANNEL_OPS, {"type": "lost_person_found", "id": case.id,
                                      "case_no": case.case_no})
    audit.record(db, principal, "lost_person.found", object_type="lost_person_case",
                 object_id=case_id, ip=client_ip(request))
    return LostPersonOut.model_validate(case)


@router.post("/{case_id}/reunite", response_model=LostPersonOut,
             summary="Confirm reunion and close the case")
async def reunite(case_id: str, principal: Principal = Depends(require_roles(*FIELD)),
                  db: Session = Depends(get_db)) -> LostPersonOut:
    case = db.get(LostPersonCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "case not found")

    case.status = "reunited"
    case.reunited_at = datetime.now(timezone.utc)

    # Clear the missing flag on the group member, if the case came from a group.
    if case.group_member_id:
        member = db.get(GroupMember, case.group_member_id)
        if member:
            member.missing_since = None

    # Close the matching field task so no one keeps searching.
    tasks = db.scalars(select(Task).where(Task.kind == "lost_person")).all()
    for task in tasks:
        if (task.payload or {}).get("case_id") == case_id and task.state != "done":
            task.state = "done"
            task.completed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(case)

    await broker.publish(CHANNEL_OPS, {"type": "lost_person_reunited", "id": case.id,
                                      "case_no": case.case_no})
    audit.record(db, principal, "lost_person.reunite", object_type="lost_person_case",
                 object_id=case_id)
    return LostPersonOut.model_validate(case)
