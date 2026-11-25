"""Communications and accountability: alerts, delivery records, audit log."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Alert(Base):
    """Announcement or critical alert.

    Text is stored per language so the app can render in the visitor's chosen language
    without a translation call at read time. Critical alerts are pinned and cannot be
    dismissed until read; they always go out on at least two channels.
    """

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(16), default="info")  # info | critical
    category: Mapped[str] = mapped_column(String(32), default="general")  # crowd | weather | route | safety | service
    title_i18n: Mapped[dict] = mapped_column(JSON, default=dict)  # {"hi": "...", "en": "..."}
    body_i18n: Mapped[dict] = mapped_column(JSON, default=dict)
    zones: Mapped[list] = mapped_column(JSON, default=list)          # [] = all zones
    languages: Mapped[list] = mapped_column(JSON, default=list)      # [] = all languages
    audience: Mapped[str] = mapped_column(String(24), default="all")  # all | visitors | field | agency
    channels: Mapped[list] = mapped_column(JSON, default=lambda: ["push"])
    requires_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default="published")  # draft | published | withdrawn
    created_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AlertDelivery(Base):
    """Per-channel fan-out result, so a silent push failure is visible to the control room."""

    __tablename__ = "alert_deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    alert_id: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(16))  # push | sms | pa | in_app
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AlertReceipt(Base):
    """Read receipt for alerts that must be acknowledged."""

    __tablename__ = "alert_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    alert_id: Mapped[str] = mapped_column(String(36), index=True)
    principal_id: Mapped[str] = mapped_column(String(36), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Every access to personal data and every sensitive action.

    Append-only by policy: no update or delete endpoint exists, and the production role
    for the API has INSERT/SELECT only on this table.
    """

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(24))
    agency: Mapped[str | None] = mapped_column(String(48))
    action: Mapped[str] = mapped_column(String(48), index=True)  # visitor.read | idcard.scan | alert.broadcast ...
    object_type: Mapped[str | None] = mapped_column(String(32))
    object_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(48))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
