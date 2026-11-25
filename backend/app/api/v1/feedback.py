"""Complaints and feedback, linked into the dashboard ticket system."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_principal, require_roles
from app.core.security import Principal, new_reference
from app.db.base import get_db
from app.models.ops import Feedback
from app.schemas import FeedbackCreate, FeedbackOut
from app.services import audit

router = APIRouter(prefix="/feedback", tags=["feedback"])

AGENCY_BY_CATEGORY = {
    "sanitation": "municipal",
    "water": "jal_sansthan",
    "safety": "police",
    "transport": "transport",
    "staff": "admin",
    "other": "admin",
}
CONTROL = ("control_room", "agency_admin", "admin")


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED,
             summary="File a complaint with photo and location")
def file_complaint(payload: FeedbackCreate,
                   principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)) -> FeedbackOut:
    if payload.client_ref:
        existing = db.scalars(
            select(Feedback).where(Feedback.client_ref == payload.client_ref)
        ).first()
        if existing:
            return FeedbackOut.model_validate(existing)

    complaint = Feedback(
        ticket_no=new_reference("GRV"),
        visitor_id=principal.subject if not principal.is_official else None,
        category=payload.category,
        description=payload.description,
        lat=payload.lat,
        lon=payload.lon,
        photo_ref=payload.photo_ref,
        agency=AGENCY_BY_CATEGORY.get(payload.category, "admin"),
        client_ref=payload.client_ref,
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)
    audit.record(db, principal, "feedback.create", object_type="feedback",
                 object_id=complaint.id, category=payload.category)
    return FeedbackOut.model_validate(complaint)


@router.get("/mine", response_model=List[FeedbackOut], summary="My complaints")
def mine(principal: Principal = Depends(get_principal),
         db: Session = Depends(get_db)) -> List[FeedbackOut]:
    stmt = select(Feedback).where(Feedback.visitor_id == principal.subject).order_by(
        Feedback.created_at.desc()
    )
    return [FeedbackOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.get("", response_model=List[FeedbackOut], summary="Agency ticket queue")
def queue(
    complaint_status: Optional[str] = Query(default=None, alias="status"),
    agency: Optional[str] = None,
    principal: Principal = Depends(require_roles(*CONTROL)),
    db: Session = Depends(get_db),
) -> List[FeedbackOut]:
    stmt = select(Feedback).order_by(Feedback.created_at.desc())
    if complaint_status:
        stmt = stmt.where(Feedback.status == complaint_status)
    if agency:
        stmt = stmt.where(Feedback.agency == agency)
    return [FeedbackOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.post("/{feedback_id}/resolve", response_model=FeedbackOut, summary="Close a complaint")
def resolve(feedback_id: str, principal: Principal = Depends(require_roles(*CONTROL)),
            db: Session = Depends(get_db)) -> FeedbackOut:
    complaint = db.get(Feedback, feedback_id)
    if complaint is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "complaint not found")
    complaint.status = "resolved"
    complaint.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(complaint)
    audit.record(db, principal, "feedback.resolve", object_type="feedback", object_id=feedback_id)
    return FeedbackOut.model_validate(complaint)
