"""Shared FastAPI dependencies: current principal, role gates, client IP."""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import Principal, TokenError, decode_token
from app.db.base import get_db

bearer = HTTPBearer(auto_error=False, description="Bearer JWT from /v1/auth/otp/verify")


def get_principal(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Principal:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        return decode_token(creds.credentials)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc),
                            headers={"WWW-Authenticate": "Bearer"}) from exc


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Dependency factory: 403 unless the caller holds one of `roles`."""

    allowed = set(roles)

    def _gate(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role '{principal.role}' cannot perform this action",
            )
        return principal

    return _gate


def client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def db_session(db: Session = Depends(get_db)) -> Session:
    return db


VisitorOnly = Depends(require_roles("visitor"))
FieldStaff = Depends(require_roles("officer", "supervisor", "control_room", "agency_admin", "admin", "volunteer"))
ControlRoom = Depends(require_roles("control_room", "agency_admin", "admin"))


def any_of(roles: Iterable[str]) -> Callable[..., Principal]:
    return require_roles(*roles)
