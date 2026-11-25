"""Alerts and broadcast.

Multi-channel by design: push, SMS and public address, so no single channel is a single
point of failure. Critical alerts always carry at least two channels — the API adds SMS
if the caller sent push only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_principal, require_roles
from app.core.security import Principal
from app.db.base import get_db
from app.models.comms import Alert, AlertDelivery, AlertReceipt
from app.models.identity import Visitor
from app.schemas import AlertCreate, AlertDeliveryOut, AlertOut, BroadcastOut
from app.services import audit, events
from app.services.realtime import CHANNEL_ALERTS, broker

router = APIRouter(prefix="/alerts", tags=["alerts"])

CONTROL = ("control_room", "agency_admin", "admin")


def _localise(alert: Alert, language: str) -> dict:
    """Fall back to Hindi, then English, then any available language."""
    def pick(store: dict) -> str:
        for code in (language, "hi", "en"):
            if store.get(code):
                return store[code]
        return next(iter(store.values()), "")

    return {
        "title": pick(alert.title_i18n or {}),
        "body": pick(alert.body_i18n or {}),
        "language_used": next(
            (c for c in (language, "hi", "en") if (alert.title_i18n or {}).get(c)), "en"
        ),
    }


@router.get("", summary="Alerts for me, in my language and zone")
def list_alerts(
    language: str = Query(default="hi"),
    zone: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
) -> List[dict]:
    stmt = select(Alert).where(Alert.status == "published").order_by(
        Alert.kind.desc(), Alert.created_at.desc()
    ).limit(limit)
    now = datetime.now(timezone.utc)
    rows = db.scalars(stmt).all()

    out = []
    for alert in rows:
        if alert.expires_at and alert.expires_at.replace(tzinfo=timezone.utc) < now:
            continue
        if alert.zones and zone and zone not in alert.zones:
            continue
        if alert.zones and not zone:
            continue  # zone-scoped alert is not shown outside its zones
        payload = AlertOut.model_validate(alert).model_dump()
        payload.update(_localise(alert, language))
        payload["pinned"] = alert.kind == "critical"
        payload["dismissible"] = alert.kind != "critical"
        out.append(payload)
    return out


@router.post("", response_model=BroadcastOut, status_code=status.HTTP_201_CREATED,
             summary="Control room: broadcast an announcement or critical alert")
async def broadcast(
    payload: AlertCreate,
    request: Request,
    principal: Principal = Depends(require_roles(*CONTROL)),
    db: Session = Depends(get_db),
) -> BroadcastOut:
    channels = list(dict.fromkeys(payload.channels))
    if payload.kind == "critical" and len(channels) < 2:
        # Rule from the design: a critical alert never rides a single channel.
        channels.append("sms" if "push" in channels else "push")

    alert = Alert(
        kind=payload.kind,
        category=payload.category,
        title_i18n=payload.title_i18n,
        body_i18n=payload.body_i18n,
        zones=payload.zones,
        languages=payload.languages,
        audience=payload.audience,
        channels=channels,
        requires_ack=payload.requires_ack or payload.kind == "critical",
        status="published",
        created_by=principal.subject,
        expires_at=payload.expires_at,
    )
    db.add(alert)
    db.flush()

    # Recipient count per channel; the actual fan-out happens in the worker.
    total_visitors = int(db.scalar(
        select(func.count()).select_from(Visitor).where(Visitor.is_active.is_(True))
    ) or 0)
    if payload.audience != "visitors":
        total_visitors = max(total_visitors, 1)

    deliveries: List[AlertDelivery] = []
    degraded: List[str] = []
    for channel in channels:
        if channel in {"push", "sms"} and total_visitors == 0:
            degraded.append(channel)
            record = AlertDelivery(alert_id=alert.id, channel=channel, target_count=0,
                                   sent_count=0, failed_count=0, error="no recipients yet")
        else:
            # The worker confirms actual sends and updates these counters.
            record = AlertDelivery(alert_id=alert.id, channel=channel,
                                   target_count=total_visitors, sent_count=0, failed_count=0)
        db.add(record)
        deliveries.append(record)
    db.commit()
    db.refresh(alert)

    await events.publish(events.TOPIC_ALERT, alert.id, {
        "alert_id": alert.id, "kind": alert.kind, "zones": alert.zones,
        "languages": alert.languages, "channels": channels, "audience": alert.audience,
    })
    await broker.publish(CHANNEL_ALERTS, {
        "type": "alert", "id": alert.id, "kind": alert.kind,
        "title_i18n": alert.title_i18n, "body_i18n": alert.body_i18n,
        "zones": alert.zones, "requires_ack": alert.requires_ack,
        "created_at": alert.created_at.isoformat(),
    })

    audit.record(db, principal, "alert.broadcast", object_type="alert", object_id=alert.id,
                 ip=client_ip(request), channels=channels, zones=alert.zones,
                 kind=alert.kind, audience=alert.audience)

    return BroadcastOut(
        alert=AlertOut.model_validate(alert),
        deliveries=[AlertDeliveryOut.model_validate(d) for d in deliveries],
        degraded_channels=degraded,
    )


@router.post("/{alert_id}/read", status_code=status.HTTP_204_NO_CONTENT,
             summary="Mark a pinned alert as read (required before it can be dismissed)")
def mark_read(alert_id: str, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)) -> None:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    existing = db.scalars(
        select(AlertReceipt).where(
            AlertReceipt.alert_id == alert_id,
            AlertReceipt.principal_id == principal.subject,
        )
    ).first()
    if existing is None:
        db.add(AlertReceipt(alert_id=alert_id, principal_id=principal.subject))
        db.commit()


@router.get("/{alert_id}/deliveries", response_model=List[AlertDeliveryOut],
            summary="Delivery status per channel")
def deliveries(alert_id: str,
               principal: Principal = Depends(require_roles(*CONTROL)),
               db: Session = Depends(get_db)) -> List[AlertDeliveryOut]:
    stmt = select(AlertDelivery).where(AlertDelivery.alert_id == alert_id)
    return [AlertDeliveryOut.model_validate(row) for row in db.scalars(stmt).all()]


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Withdraw an alert")
def withdraw(alert_id: str, principal: Principal = Depends(require_roles(*CONTROL)),
             db: Session = Depends(get_db)) -> None:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    alert.status = "withdrawn"
    db.commit()
    audit.record(db, principal, "alert.withdraw", object_type="alert", object_id=alert_id)
