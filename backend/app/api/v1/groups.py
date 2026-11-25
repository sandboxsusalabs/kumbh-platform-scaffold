"""Family and group registration.

Rules from the design: members with phones accept an optional, revocable link request;
locations are visible to the group only when sharing is on or an SOS is open; the leader
can mark a member missing in one tap, which opens a lost-person case.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_principal
from app.core.security import Principal, new_reference
from app.db.base import get_db
from app.models.identity import Group, GroupMember, Visitor
from app.models.ops import LostPersonCase, SosEvent, Task
from app.schemas import (
    GroupCreate,
    GroupLocationsIn,
    GroupOut,
    LocationSharingIn,
    MemberCreate,
    MemberOut,
)
from app.services import audit
from app.services.ids import wristband_code

router = APIRouter(prefix="/groups", tags=["groups"])

MAX_MEMBERS = 20


def _own_group(db: Session, group_id: str, principal: Principal) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "group not found")
    if group.leader_visitor_id != principal.subject:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the group leader can do this")
    return group


def _sos_open_for_group(db: Session, group_id: str) -> bool:
    stmt = select(SosEvent).where(
        SosEvent.group_id == group_id,
        SosEvent.status.in_(["new", "assigned", "en_route", "on_site"]),
    )
    return db.scalars(stmt).first() is not None


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED,
             summary="Create a group (leader is the caller)")
def create_group(payload: GroupCreate, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)) -> GroupOut:
    if payload.leader_visitor_id != principal.subject:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "leader must be the caller")

    leader = db.get(Visitor, principal.subject)
    if leader is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visitor not found")

    group = Group(name=payload.name, leader_visitor_id=principal.subject, location_sharing=False)
    db.add(group)
    db.flush()

    db.add(GroupMember(
        group_id=group.id,
        visitor_id=leader.id,
        name=leader.name or "Group leader",
        age=leader.age,
        role="leader",
        invite_state="accepted",
    ))
    leader.group_id = group.id
    db.commit()
    db.refresh(group)

    audit.record(db, principal, "group.create", object_type="group", object_id=group.id)
    return GroupOut.model_validate(group)


@router.get("/{group_id}", response_model=GroupOut, summary="Group with members")
def get_group(group_id: str, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)) -> GroupOut:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "group not found")
    if group.leader_visitor_id != principal.subject and not principal.is_official:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your group")
    return GroupOut.model_validate(group)


@router.post("/{group_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED,
             summary="Add a member by phone, or by name and age for children and elders")
def add_member(group_id: str, payload: MemberCreate,
               principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)) -> MemberOut:
    group = _own_group(db, group_id, principal)

    existing = db.scalars(select(GroupMember).where(GroupMember.group_id == group.id)).all()
    if len(existing) >= MAX_MEMBERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"group limit is {MAX_MEMBERS} members")

    visitor_id = None
    invite_state = "accepted"
    code = None

    if payload.phone:
        visitor = db.scalars(select(Visitor).where(Visitor.phone == payload.phone)).first()
        if visitor is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND,
                                "that number is not registered yet; ask them to register first")
        visitor_id = visitor.id
        invite_state = "pending"  # optional, revocable link request
        visitor.group_id = group.id
    else:
        # No phone: child or elder. They get a wristband QR at a help desk.
        code = wristband_code()

    member = GroupMember(
        group_id=group.id,
        visitor_id=visitor_id,
        name=payload.name,
        age=payload.age,
        is_minor=payload.is_minor or (payload.age is not None and payload.age < 18),
        guardian_member_id=payload.guardian_member_id,
        invite_state=invite_state,
        wristband_code=code,
        role="member",
    )
    db.add(member)
    db.commit()
    db.refresh(member)

    audit.record(db, principal, "group.member_add", object_type="group_member",
                 object_id=member.id, via="phone" if payload.phone else "name_age")
    return MemberOut.model_validate(member)


@router.post("/{group_id}/members/{member_id}/accept", response_model=MemberOut,
             summary="Member accepts a link request")
def accept_invite(group_id: str, member_id: str, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)) -> MemberOut:
    member = db.get(GroupMember, member_id)
    if member is None or member.group_id != group_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    if member.visitor_id != principal.subject:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this invite is not for you")
    member.invite_state = "accepted"
    db.commit()
    db.refresh(member)
    return MemberOut.model_validate(member)


@router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT,
               summary="Revoke a member link")
def revoke_member(group_id: str, member_id: str, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)) -> None:
    group = _own_group(db, group_id, principal)
    member = db.get(GroupMember, member_id)
    if member is None or member.group_id != group.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    if member.role == "leader":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the leader cannot be removed")
    member.invite_state = "revoked"
    if member.visitor_id:
        visitor = db.get(Visitor, member.visitor_id)
        if visitor:
            visitor.group_id = None
    db.commit()
    audit.record(db, principal, "group.member_revoke", object_type="group_member", object_id=member_id)


@router.post("/{group_id}/location-sharing", response_model=GroupOut,
             summary="Turn group location sharing on or off")
def set_sharing(group_id: str, payload: LocationSharingIn,
                principal: Principal = Depends(get_principal),
                db: Session = Depends(get_db)) -> GroupOut:
    group = _own_group(db, group_id, principal)
    group.location_sharing = payload.enabled
    db.commit()
    db.refresh(group)
    audit.record(db, principal, "group.sharing", object_type="group", object_id=group.id,
                 enabled=payload.enabled)
    return GroupOut.model_validate(group)


@router.post("/{group_id}/locations", summary="Member locations (only while sharing or during SOS)")
def group_locations(group_id: str, payload: GroupLocationsIn,
                    principal: Principal = Depends(get_principal),
                    db: Session = Depends(get_db)) -> dict:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "group not found")

    sos_open = _sos_open_for_group(db, group.id)
    if not group.location_sharing and not sos_open:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "group location sharing is off; members cannot share locations")

    members = db.scalars(select(GroupMember).where(GroupMember.group_id == group.id)).all()
    by_visitor = {m.visitor_id: m for m in members if m.visitor_id}
    if principal.subject not in by_visitor and not principal.is_official:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your group")

    # Members push their own point; the leader reads everyone's.
    for item in payload.locations:
        visitor = db.get(Visitor, item.get("visitor_id", ""))
        if visitor is None or visitor.group_id != group.id:
            continue
        visitor.last_lat = item.get("lat")
        visitor.last_lon = item.get("lon")
        visitor.last_location_at = datetime.now(timezone.utc)
    db.commit()

    result = []
    for member in members:
        if member.visitor_id is None:
            result.append({"member_id": member.id, "name": member.name, "location": None,
                           "reason": "no phone; wristband QR only"})
            continue
        visitor = db.get(Visitor, member.visitor_id)
        result.append({
            "member_id": member.id,
            "name": member.name,
            "location": (
                {"lat": visitor.last_lat, "lon": visitor.last_lon,
                 "at": visitor.last_location_at.isoformat() if visitor.last_location_at else None}
                if visitor and visitor.last_lat is not None else None
            ),
            "missing_since": member.missing_since.isoformat() if member.missing_since else None,
        })
    return {"group_id": group.id, "sharing": group.location_sharing, "sos_open": sos_open,
            "members": result}


@router.post("/{group_id}/members/{member_id}/missing", status_code=status.HTTP_201_CREATED,
             summary="One tap: mark a member missing and open a lost-person case")
def mark_missing(group_id: str, member_id: str,
                 principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)) -> dict:
    group = _own_group(db, group_id, principal)
    member = db.get(GroupMember, member_id)
    if member is None or member.group_id != group.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")

    member.missing_since = datetime.now(timezone.utc)

    case = LostPersonCase(
        case_no=new_reference("LP"),
        reported_by_visitor_id=principal.subject,
        group_member_id=member.id,
        subject_name=member.name,
        subject_age=member.age,
        is_child=member.is_minor,
        status="open",
        last_seen_at=member.missing_since,
    )
    db.add(case)
    db.flush()

    task = Task(
        code=new_reference("T"),
        kind="lost_person",
        title=f"Locate missing person: {member.name}",
        zone_code=None,
        priority=1,
        payload={"case_id": case.id, "case_no": case.case_no, "wristband": member.wristband_code},
    )
    db.add(task)
    db.commit()

    audit.record(db, principal, "lost_person.open", object_type="lost_person_case",
                 object_id=case.id, source="group_missing_mark")
    return {"case_id": case.id, "case_no": case.case_no, "task_id": task.id,
            "status": "open", "next": "Control room and nearest lost-and-found centre notified"}
