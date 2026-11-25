"""Visitor profile, digital ID and the officer QR scan view."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, require_roles
from app.core.security import ROLE_VISITOR, SCAN_ROLES, Principal
from app.db.base import get_db
from app.models.identity import Group, Visitor
from app.schemas import IdCardOut, ScanViewOut, VisitorCreate, VisitorOut
from app.services import audit
from app.services.ids import offline_card, qr_payload, resolve_reference

router = APIRouter(prefix="/visitors", tags=["visitors"])


def _load_visitor(db: Session, visitor_id: str) -> Visitor:
    visitor = db.get(Visitor, visitor_id)
    if visitor is None or not visitor.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "visitor not found")
    return visitor


@router.post("", response_model=VisitorOut, status_code=status.HTTP_201_CREATED,
             summary="Complete registration (step 2 of 4)")
def register(
    payload: VisitorCreate,
    request: Request,
    principal: Principal = Depends(require_roles(ROLE_VISITOR)),
    db: Session = Depends(get_db),
) -> VisitorOut:
    """Name, age, gender, home state, language and up to two emergency contacts.

    Aadhaar/DigiLocker is optional and only the fact of verification is recorded —
    the identifier is never written to our database.
    """
    visitor = _load_visitor(db, principal.subject)

    visitor.name = payload.name
    visitor.age = payload.age
    visitor.gender = payload.gender
    visitor.home_state = payload.home_state
    visitor.language = payload.language
    visitor.emergency_contacts = payload.emergency_contacts
    visitor.accessibility_needs = payload.accessibility_needs
    visitor.large_text = payload.large_text

    if payload.verification:
        visitor.verification_method = payload.verification
        visitor.verified_at = datetime.now(timezone.utc)

    if visitor.id_card_issued_at is None:
        visitor.id_card_issued_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(visitor)

    audit.record(db, principal, "visitor.register", object_type="visitor",
                 object_id=visitor.id, ip=client_ip(request), language=payload.language)
    return VisitorOut.model_validate(visitor)


@router.get("/me", response_model=VisitorOut, summary="My profile")
def me(principal: Principal = Depends(require_roles(ROLE_VISITOR)),
       db: Session = Depends(get_db)) -> VisitorOut:
    return VisitorOut.model_validate(_load_visitor(db, principal.subject))


@router.patch("/me", response_model=VisitorOut, summary="Update language or accessibility settings")
def update_me(
    language: str | None = None,
    large_text: bool | None = None,
    principal: Principal = Depends(require_roles(ROLE_VISITOR)),
    db: Session = Depends(get_db),
) -> VisitorOut:
    visitor = _load_visitor(db, principal.subject)
    if language:
        visitor.language = language
    if large_text is not None:
        visitor.large_text = large_text
    db.commit()
    db.refresh(visitor)
    return VisitorOut.model_validate(visitor)


@router.get("/me/id-card", response_model=IdCardOut, summary="Digital ID with offline card")
def id_card(principal: Principal = Depends(require_roles(ROLE_VISITOR)),
            db: Session = Depends(get_db)) -> IdCardOut:
    """The QR encodes an opaque reference; `offline_token` keeps the ID usable offline."""
    visitor = _load_visitor(db, principal.subject)
    card = offline_card(visitor)
    return IdCardOut(
        visitor_id=visitor.id,
        qr_payload=card["qr_payload"],
        offline_token=card["token"],
        issued_at=card["issued_at"],
        valid_until=card["valid_until"],
        qr_hint=card["qr_hint"],
    )


@router.post("/me/location", status_code=status.HTTP_204_NO_CONTENT,
             summary="Push last known location (kept only for the event period)")
def push_location(
    lat: float,
    lon: float,
    principal: Principal = Depends(require_roles(ROLE_VISITOR)),
    db: Session = Depends(get_db),
) -> None:
    visitor = _load_visitor(db, principal.subject)
    visitor.last_lat = lat
    visitor.last_lon = lon
    visitor.last_location_at = datetime.now(timezone.utc)
    db.commit()


@router.get("/{visitor_id}/scan-view", response_model=ScanViewOut,
            summary="Officer QR scan: minimum details, audited")
def scan_view(
    visitor_id: str,
    request: Request,
    principal: Principal = Depends(require_roles(*SCAN_ROLES)),
    db: Session = Depends(get_db),
) -> ScanViewOut:
    """Resolves either a visitor id or an ID-card reference (what the QR encodes)."""
    visitor = db.get(Visitor, visitor_id) or resolve_reference(db, visitor_id)
    if visitor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown visitor reference")

    group = db.get(Group, visitor.group_id) if visitor.group_id else None

    # The promise in the privacy notice: every official access is logged.
    audit.record(db, principal, "idcard.scan", object_type="visitor", object_id=visitor.id,
                 ip=client_ip(request), agency=principal.agency)

    return ScanViewOut(
        visitor_ref=visitor.id_card_token,
        name=visitor.name,
        age=visitor.age,
        group_id=visitor.group_id,
        group_name=group.name if group else None,
        emergency_contacts=visitor.emergency_contacts or [],
        language=visitor.language,
        scanned_by=principal.name or principal.subject,
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT,
               summary="Erase my data (DPDP Act right to erasure)")
def erase_me(principal: Principal = Depends(require_roles(ROLE_VISITOR)),
             db: Session = Depends(get_db)) -> None:
    """Soft delete: the row is deactivated and personal fields are cleared. Case records
    that an agency must keep (SOS, lost person) retain only the reference, not the profile."""
    visitor = _load_visitor(db, principal.subject)
    visitor.is_active = False
    visitor.name = None
    visitor.age = None
    visitor.emergency_contacts = []
    visitor.last_lat = None
    visitor.last_lon = None
    db.commit()
    audit.record(db, principal, "visitor.erase", object_type="visitor", object_id=visitor.id)
