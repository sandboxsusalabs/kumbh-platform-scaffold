"""Identity: visitors, OTP challenges, families and groups."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Visitor(Base):
    """A registered pilgrim.

    Personal data is deliberately minimal: no Aadhaar number is ever stored — only a
    boolean saying the visitor chose to verify, and the verification reference.
    """

    __tablename__ = "visitors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    phone: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(16))
    home_state: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="hi")

    # Emergency contacts: [{"name": ..., "phone": ..., "relation": ...}]  (1–2 entries)
    emergency_contacts: Mapped[list] = mapped_column(JSON, default=list)

    # QR payload is an opaque reference; `id_card_token` is what the QR encodes.
    id_card_token: Mapped[str] = mapped_column(String(48), unique=True, index=True, default=lambda: _uuid().replace("-", "")[:20])
    id_card_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Optional verification, only when the visitor chooses it.
    verification_method: Mapped[str | None] = mapped_column(String(16))  # aadhaar | digilocker | None
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Accessibility needs drive the map (wheelchair routes) and assistance requests.
    accessibility_needs: Mapped[list] = mapped_column(JSON, default=list)
    large_text: Mapped[bool] = mapped_column(Boolean, default=False)

    group_id: Mapped[str | None] = mapped_column(ForeignKey("groups.id", ondelete="SET NULL"))
    last_lat: Mapped[float | None] = mapped_column()
    last_lon: Mapped[float | None] = mapped_column()
    last_location_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    memberships: Mapped[list["GroupMember"]] = relationship(back_populates="visitor")


class OtpRequest(Base):
    __tablename__ = "otp_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    phone: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Group(Base):
    """A family or travelling party. One leader, several members.

    Location sharing inside a group is off until the group turns it on, or until an
    SOS is raised — that is the only automatic exception.
    """

    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120))
    leader_visitor_id: Mapped[str] = mapped_column(String(36), index=True)
    location_sharing: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list["GroupMember"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class GroupMember(Base):
    """A person in a group.

    `visitor_id` is empty for children and elders without a phone: they exist only as
    a name and age, with a wristband code printed at a help desk.
    """

    __tablename__ = "group_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), index=True)
    visitor_id: Mapped[str | None] = mapped_column(ForeignKey("visitors.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120))
    age: Mapped[int | None] = mapped_column(Integer)
    is_minor: Mapped[bool] = mapped_column(Boolean, default=False)
    wristband_code: Mapped[str | None] = mapped_column(String(24), unique=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # leader | member
    invite_state: Mapped[str] = mapped_column(String(16), default="accepted")  # pending | accepted | revoked
    guardian_member_id: Mapped[str | None] = mapped_column(String(36))
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    group: Mapped[Group] = relationship(back_populates="members")
    visitor: Mapped[Visitor | None] = relationship(back_populates="memberships")


class Officer(Base):
    """Dashboard and field-app user. Seeded from the administration's staff list."""

    __tablename__ = "officers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(16), unique=True)
    role: Mapped[str] = mapped_column(String(24), default="officer")
    agency: Mapped[str] = mapped_column(String(48))  # police | health | fire | municipal | transport | admin
    zone: Mapped[str | None] = mapped_column(String(24))
    totp_secret: Mapped[str | None] = mapped_column(Text)  # MFA for officials
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
