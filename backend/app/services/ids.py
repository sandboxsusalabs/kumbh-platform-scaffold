"""Digital visitor ID.

The QR encodes an opaque reference only — never a name, phone or Aadhaar. A scan
resolves the reference server-side, after officer login, and the lookup is audited.

`offline_token` is a signed, short, self-contained card payload so the ID screen still
works with no network at the ghat. It carries the minimum needed to prove registration
(visitor reference, issue date, expiry) and nothing that identifies the person.
"""
from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from app.core.config import settings
from app.core.security import _b64encode, _sign, decode_token
from app.models.identity import Visitor

OFFLINE_ID_PREFIX = "KMID1"
DEFAULT_VALID_DAYS = 45


def qr_payload(visitor: Visitor) -> str:
    """What gets printed into the QR image."""
    return f"KUMBH:VID:{visitor.id_card_token}"


def offline_card(visitor: Visitor, valid_days: int = DEFAULT_VALID_DAYS) -> Dict[str, Any]:
    """Signed card payload, verifiable offline by the field app with the same key."""
    issued = datetime.now(timezone.utc)
    body = {
        "v": 1,
        "ref": visitor.id_card_token,
        "lang": visitor.language,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(days=valid_days)).timestamp()),
        "grp": visitor.group_id,
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    signature = _b64encode(_sign(raw))[:32]
    token = f"{OFFLINE_ID_PREFIX}.{_b64encode(raw)}.{signature}"
    return {
        "token": token,
        "issued_at": issued.isoformat(),
        "valid_until": (issued + timedelta(days=valid_days)).isoformat(),
        "qr_payload": qr_payload(visitor),
        "qr_hint": "QR carries an ID reference only; no personal data is encoded.",
    }


def read_offline_card(token: str) -> Dict[str, Any]:
    """Field-app verification path. Raises ValueError on tampering or expiry."""
    try:
        prefix, raw, signature = token.split(".")
    except ValueError as exc:
        raise ValueError("malformed card") from exc
    if prefix != OFFLINE_ID_PREFIX:
        raise ValueError("unknown card version")

    raw_bytes = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if _b64encode(_sign(raw_bytes))[:32] != signature:
        raise ValueError("bad signature")

    body = json.loads(raw_bytes)
    if body.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
        raise ValueError("card expired")
    return body


def wristband_code() -> str:
    """Printed QR for a child or elder without a phone, linked to a guardian."""
    return "WB" + secrets.token_hex(4).upper()


def resolve_reference(db, reference: str) -> Visitor | None:
    from sqlalchemy import select

    stmt = select(Visitor).where(Visitor.id_card_token == reference)
    return db.scalars(stmt).first()


__all__ = ["qr_payload", "offline_card", "read_offline_card", "wristband_code",
           "resolve_reference", "decode_token", "settings"]
