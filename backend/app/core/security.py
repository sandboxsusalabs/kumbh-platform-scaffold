"""Authentication primitives.

Visitor auth is phone + OTP only. Officials additionally need MFA (TOTP) before a
dashboard token is issued — see `api/v1/auth.py`. Tokens are HS256 JWTs signed with
`JWT_SECRET`; in production the key comes from the cloud secret manager and is rotated
on the schedule agreed with the administration.

Kept dependency-free on purpose: `hmac` + `hashlib` + `base64` from the standard library,
so the scaffold installs and tests with nothing extra.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.core.config import settings

# Roles, narrowest to widest. A principal holds exactly one.
ROLE_VISITOR = "visitor"
ROLE_VOLUNTEER = "volunteer"
ROLE_OFFICER = "officer"
ROLE_SUPERVISOR = "supervisor"
ROLE_CONTROL_ROOM = "control_room"
ROLE_AGENCY_ADMIN = "agency_admin"
ROLE_ADMIN = "admin"

# Actions that need a higher role and are always audited.
SENSITIVE_ROLES = {
    ROLE_CONTROL_ROOM,
    ROLE_AGENCY_ADMIN,
    ROLE_ADMIN,
}

# Roles allowed to see a visitor's minimum identifying fields by QR scan.
SCAN_ROLES = {ROLE_OFFICER, ROLE_SUPERVISOR, ROLE_CONTROL_ROOM, ROLE_AGENCY_ADMIN, ROLE_ADMIN}


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired or wrongly signed."""


@dataclass(frozen=True)
class Principal:
    """Who is calling, and in what scope."""

    subject: str
    role: str
    agency: Optional[str] = None
    zone: Optional[str] = None
    name: Optional[str] = None

    @property
    def is_official(self) -> bool:
        return self.role != ROLE_VISITOR

    def to_dict(self) -> Dict[str, Any]:
        return {"sub": self.subject, "role": self.role, "agency": self.agency,
                "zone": self.zone, "name": self.name}


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(message: bytes) -> bytes:
    return hmac.new(settings.jwt_secret.encode("utf-8"), message, hashlib.sha256).digest()


def create_token(principal: Principal, ttl_seconds: Optional[int] = None) -> str:
    now = int(time.time())
    payload = principal.to_dict()
    payload.update({"iat": now, "exp": now + (ttl_seconds or settings.jwt_ttl_seconds)})
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{header}.{body}".encode("ascii")
    return f"{header}.{body}.{_b64encode(_sign(signing_input))}"


def decode_token(token: str) -> Principal:
    try:
        header, body, signature = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc

    expected = _b64encode(_sign(f"{header}.{body}".encode("ascii")))
    if not hmac.compare_digest(expected, signature):
        raise TokenError("bad signature")

    try:
        payload = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("bad payload") from exc

    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("token expired")

    return Principal(
        subject=str(payload.get("sub")),
        role=str(payload.get("role")),
        agency=payload.get("agency"),
        zone=payload.get("zone"),
        name=payload.get("name"),
    )


def hash_otp(code: str, phone: str) -> str:
    """OTP is never stored in clear text."""
    return hmac.new(settings.jwt_secret.encode(), f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def generate_otp() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(settings.otp_length))


def new_reference(prefix: str) -> str:
    """Human-readable reference for cases and tickets: SOS-7F3A2C1B."""
    return f"{prefix}-{secrets.token_hex(4).upper()}"
