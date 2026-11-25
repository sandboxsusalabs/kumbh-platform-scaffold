"""Operations: SOS, incidents, lost-person cases, field tasks, complaints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


SOS_STATES = ["new", "assigned", "en_route", "on_site", "closed", "cancelled"]
TASK_STATES = ["assigned", "accepted", "en_route", "on_site", "done", "cancelled"]


class SosEvent(Base):
    """A distress call.

    Written to the database first and published to the priority queue second, so a
    queue outage never loses a call. `channel` records whether the alert arrived over
    data, SMS or a helpline call — the SMS fallback path is what makes SOS work on a
    dead network.
    """

    __tablename__ = "sos_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    visitor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    group_id: Mapped[str | None] = mapped_column(String(36))
    category: Mapped[str] = mapped_column(String(24), default="medical")  # medical | police | fire | lost_child | other
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    is_silent: Mapped[bool] = mapped_column(Boolean, default=False)
    channel: Mapped[str] = mapped_column(String(16), default="data")  # data | sms | voice | ussd
    priority: Mapped[int] = mapped_column(Integer, default=1)  # 1 highest
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    assigned_team: Mapped[str | None] = mapped_column(String(48))
    assigned_task_id: Mapped[str | None] = mapped_column(String(36))
    acknowledged_by: Mapped[str | None] = mapped_column(String(36))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    client_ref: Mapped[str | None] = mapped_column(String(64), unique=True)  # offline dedupe
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Incident(Base):
    """Field report: photo, voice note and location in under 30 seconds, queued offline."""

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    reporter_id: Mapped[str | None] = mapped_column(String(36), index=True)
    reporter_role: Mapped[str] = mapped_column(String(24), default="officer")
    kind: Mapped[str] = mapped_column(String(32))  # crowd_crush | medical | fire | fault | other
    description: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    zone_code: Mapped[str | None] = mapped_column(String(24))
    photo_ref: Mapped[str | None] = mapped_column(String(240))
    voice_ref: Mapped[str | None] = mapped_column(String(240))
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    client_ref: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at_client: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LostPersonCase(Base):
    """Registry shared by the visitor app, the dashboard lost-and-found desk and the
    field app's desk mode, so a found child can be matched against open cases."""

    __tablename__ = "lost_person_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_no: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    reported_by_visitor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    group_member_id: Mapped[str | None] = mapped_column(String(36))
    subject_name: Mapped[str] = mapped_column(String(120))
    subject_age: Mapped[int | None] = mapped_column(Integer)
    subject_gender: Mapped[str | None] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text)
    photo_ref: Mapped[str | None] = mapped_column(Text)
    last_seen_lat: Mapped[float | None] = mapped_column(Float)
    last_seen_lon: Mapped[float | None] = mapped_column(Float)
    last_seen_place: Mapped[str | None] = mapped_column(String(160))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    languages_spoken: Mapped[str | None] = mapped_column(String(240))
    medical_needs: Mapped[str | None] = mapped_column(String(500))
    reporter_name: Mapped[str | None] = mapped_column(String(120))
    reporter_phone: Mapped[str | None] = mapped_column(String(10), index=True)
    reporter_relation: Mapped[str | None] = mapped_column(String(40))
    alternate_phone: Mapped[str | None] = mapped_column(String(10))
    reporter_location: Mapped[str | None] = mapped_column(String(160))
    centre_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | sighting | matched | reunited | closed
    status_changed_by: Mapped[str | None] = mapped_column(String(36))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_child: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    reunited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LostPersonSighting(Base):
    __tablename__ = "lost_person_sightings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    reported_by: Mapped[str] = mapped_column(String(36))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    """A job pushed to the field app: SOS response, cleaning round, barricade check."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32))  # sos_response | cleaning | inspection | barricade | lost_person
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    zone_code: Mapped[str | None] = mapped_column(String(24), index=True)
    assignee_id: Mapped[str | None] = mapped_column(String(36), index=True)
    assignee_team: Mapped[str | None] = mapped_column(String(48))
    agency: Mapped[str | None] = mapped_column(String(48))
    priority: Mapped[int] = mapped_column(Integer, default=2)
    state: Mapped[str] = mapped_column(String(16), default="assigned", index=True)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskEvent(Base):
    """State transition with the officer's geotagged proof."""

    __tablename__ = "task_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    state: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(String(36))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    photo_ref: Mapped[str | None] = mapped_column(String(240))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Feedback(Base):
    """Complaint from the visitor app, tied into the dashboard ticket system."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticket_no: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    visitor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    category: Mapped[str] = mapped_column(String(32))  # sanitation | water | safety | transport | staff | other
    description: Mapped[str] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    photo_ref: Mapped[str | None] = mapped_column(String(240))
    agency: Mapped[str | None] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    client_ref: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
