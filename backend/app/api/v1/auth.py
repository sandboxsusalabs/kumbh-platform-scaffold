"""Authentication: visitor OTP, officer login with MFA, token refresh."""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_principal
from app.core.config import settings
from app.core.security import (
    ROLE_VISITOR,
    Principal,
    create_token,
)
from app.db.base import get_db
from app.models.identity import Officer, Visitor
from app.schemas import OfficerLoginIn, OtpRequestIn, OtpRequestOut, OtpVerifyIn, TokenOut
from app.services import audit, otp

router = APIRouter(prefix="/auth", tags=["auth"])


def _totp_verify(secret_b32: str, code: str, window: int = 1) -> bool:
    """RFC 6238 TOTP, 30-second step, 6 digits — the MFA factor for officials."""
    try:
        key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    except Exception:  # noqa: BLE001
        return False
    counter = int(time.time() // 30)
    for offset in range(-window, window + 1):
        digest = hmac.new(key, struct.pack(">Q", counter + offset), hashlib.sha1).digest()
        index = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF
        if f"{value % 1_000_000:06d}" == code.strip():
            return True
    return False


@router.post("/otp/request", response_model=OtpRequestOut, summary="Send a login OTP")
def request_otp(payload: OtpRequestIn, db: Session = Depends(get_db)) -> OtpRequestOut:
    if otp.rate_limited(payload.phone):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many OTP requests, retry later")
    challenge, code = otp.issue_otp(db, payload.phone)
    return OtpRequestOut(
        request_id=challenge.id,
        expires_in=settings.otp_ttl_seconds,
        dev_otp=code,
    )


@router.post("/otp/verify", response_model=TokenOut, summary="Verify OTP and get a visitor token")
def verify_otp(payload: OtpVerifyIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    if not otp.verify_otp(db, payload.request_id, payload.phone, payload.otp):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired OTP")

    visitor = db.scalars(select(Visitor).where(Visitor.phone == payload.phone)).first()
    created = False
    if visitor is None:
        visitor = Visitor(phone=payload.phone, language="hi")
        db.add(visitor)
        db.commit()
        db.refresh(visitor)
        created = True

    principal = Principal(subject=visitor.id, role=ROLE_VISITOR, name=visitor.name)
    audit.record(db, principal, "auth.login", object_type="visitor", object_id=visitor.id,
                 ip=client_ip(request), method="otp", created=created)

    return TokenOut(
        access_token=create_token(principal),
        expires_in=settings.jwt_ttl_seconds,
        role=ROLE_VISITOR,
        is_registered=bool(visitor.name),
    )


@router.post("/officer/login", response_model=TokenOut, summary="Officer / field staff login")
def officer_login(payload: OfficerLoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    """Officials log in with an OTP plus a TOTP code when MFA is enabled.

    The OTP is issued through the same `/auth/otp/request` endpoint using the officer's
    registered phone, so one gateway serves both populations.
    """
    officer = db.scalars(select(Officer).where(Officer.employee_code == payload.employee_code)).first()
    if officer is None or not officer.is_active or officer.phone != payload.phone:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or inactive officer")

    if settings.officer_mfa_required:
        if not payload.totp:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA code required")
        if not officer.totp_secret or not _totp_verify(officer.totp_secret, payload.totp):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid MFA code")

    principal = Principal(
        subject=officer.id,
        role=officer.role,
        agency=officer.agency,
        zone=officer.zone,
        name=officer.name,
    )
    audit.record(db, principal, "auth.officer_login", object_type="officer",
                 object_id=officer.id, ip=client_ip(request))

    return TokenOut(
        access_token=create_token(principal),
        expires_in=settings.jwt_ttl_seconds,
        role=officer.role,
        is_registered=True,
    )


@router.get("/me", summary="Echo the current token's scope")
def whoami(principal: Principal = Depends(get_principal)) -> dict:
    return {
        "subject": principal.subject,
        "role": principal.role,
        "agency": principal.agency,
        "zone": principal.zone,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/refresh", response_model=TokenOut, summary="Exchange a valid token for a fresh one")
def refresh(principal: Principal = Depends(get_principal)) -> TokenOut:
    return TokenOut(
        access_token=create_token(principal),
        expires_in=settings.jwt_ttl_seconds,
        role=principal.role,
        is_registered=True,
    )
