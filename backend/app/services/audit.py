"""Audit trail.

`record()` is called on every read of personal data and on every sensitive action.
It writes to the database and never raises into the request path: a failed audit write
is logged loudly, and in production it is a page-the-on-call condition because the
privacy notice promises that every official access is logged.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.security import Principal
from app.models.comms import AuditLog

log = logging.getLogger(__name__)


def record(
    db: Session,
    principal: Optional[Principal],
    action: str,
    *,
    object_type: str | None = None,
    object_id: str | None = None,
    ip: str | None = None,
    **meta: Any,
) -> None:
    entry = AuditLog(
        actor_id=principal.subject if principal else None,
        actor_role=principal.role if principal else None,
        agency=principal.agency if principal else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        ip=ip,
        meta=meta or {},
    )
    try:
        db.add(entry)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        log.error("AUDIT WRITE FAILED action=%s object=%s err=%s", action, object_id, exc)
        db.rollback()
