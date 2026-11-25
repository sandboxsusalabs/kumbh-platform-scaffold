"""OTP issuing and verification.

Storage is the database (survives an API restart on any replica), with a small
in-process rate limiter in front. In production the SMS gateway is a pluggable
provider — the send function is the single place to swap in the state's gateway.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_otp, hash_otp
from app.models.identity import OtpRequest

log = logging.getLogger(__name__)

# phone -> (window_start_epoch, count). Per-process; Redis INCR replaces this at scale.
_RATE: Dict[str, Tuple[float, int]] = {}
RATE_WINDOW_SECONDS = 600
RATE_MAX_PER_WINDOW = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    """SQLite stores naive datetimes; compare on the same footing."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def rate_limited(phone: str) -> bool:
    import time

    start, count = _RATE.get(phone, (time.time(), 0))
    if time.time() - start > RATE_WINDOW_SECONDS:
        _RATE[phone] = (time.time(), 1)
        return False
    if count >= RATE_MAX_PER_WINDOW:
        return True
    _RATE[phone] = (start, count + 1)
    return False


def send_sms(phone: str, text: str) -> None:
    """Integration seam. No gateway configured => log only, never fail the request."""
    if settings.sms_gateway_url:
        # requests/httpx call to the state gateway goes here.
        log.info("sms gateway send to %s (%d chars)", phone[-4:].rjust(len(phone), "*"), len(text))
    else:
        log.info("sms gateway not configured; OTP for %s not sent", phone)


def issue_otp(db: Session, phone: str) -> Tuple[OtpRequest, str | None]:
    """Create a challenge. Returns the plain code only when dev debug return is on."""
    code = generate_otp()
    challenge = OtpRequest(
        phone=phone,
        code_hash=hash_otp(code, phone),
        expires_at=_now() + timedelta(seconds=settings.otp_ttl_seconds),
    )
    db.add(challenge)
    db.commit()
    db.refresh(challenge)

    send_sms(phone, f"{code} is your Kumbh Mela verification code. Valid {settings.otp_ttl_seconds // 60} minutes.")
    return challenge, (code if settings.otp_debug_return else None)


def verify_otp(db: Session, request_id: str, phone: str, code: str) -> bool:
    challenge = db.get(OtpRequest, request_id)
    if challenge is None or challenge.phone != phone:
        return False
    if challenge.consumed_at is not None:
        return False
    if _naive(challenge.expires_at) < _naive(_now()):
        return False
    if challenge.attempts >= 5:
        return False

    challenge.attempts += 1
    if challenge.code_hash != hash_otp(code, phone):
        db.commit()
        return False

    challenge.consumed_at = _now()
    db.commit()
    return True


def latest_consumed(db: Session, phone: str) -> OtpRequest | None:
    stmt = (
        select(OtpRequest)
        .where(OtpRequest.phone == phone, OtpRequest.consumed_at.is_not(None))
        .order_by(OtpRequest.created_at.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()
