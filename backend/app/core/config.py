"""Application settings.

Every value comes from the environment so the same image runs in dev, staging and
the event-time production cluster. Secrets are never defaulted in prod: `Settings.validate()`
is called on startup and refuses to boot with the placeholder JWT secret outside dev.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


# Languages the platform must serve. Hindi and English first; the rest are the
# major pilgrim-origin languages named in the solution design.
SUPPORTED_LANGUAGES = ["hi", "en", "bn", "gu", "mr", "ta", "te", "pa", "or", "kn", "ml", "as", "ur"]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Haridwar Kumbh Mela Platform API"
    version: str = "0.1.0"
    env: str = field(default_factory=lambda: _env("KUMBH_ENV", "dev"))

    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "sqlite:///./kumbh_dev.db"))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL", "redis://localhost:6379/0"))
    kafka_bootstrap: str = field(default_factory=lambda: _env("KAFKA_BOOTSTRAP", ""))

    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", "dev-only-insecure-secret"))
    jwt_ttl_seconds: int = field(default_factory=lambda: _int("JWT_TTL_SECONDS", 86400))
    officer_mfa_required: bool = field(default_factory=lambda: _bool("OFFICER_MFA_REQUIRED", True))

    otp_ttl_seconds: int = field(default_factory=lambda: _int("OTP_TTL_SECONDS", 300))
    otp_length: int = field(default_factory=lambda: _int("OTP_LENGTH", 6))
    otp_debug_return: bool = field(default_factory=lambda: _bool("OTP_DEBUG_RETURN", True))

    cors_origins: List[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in _env("CORS_ORIGINS", "http://localhost:8000,http://localhost:5173").split(",")
            if o.strip()
        ]
    )

    # Integrations that are stubbed until agency API access is confirmed.
    sms_gateway_url: str = field(default_factory=lambda: _env("SMS_GATEWAY_URL"))
    push_key: str = field(default_factory=lambda: _env("PUSH_FCM_SERVER_KEY"))
    weather_api_url: str = field(default_factory=lambda: _env("WEATHER_API_URL"))
    routing_engine_url: str = field(default_factory=lambda: _env("ROUTING_ENGINE_URL"))
    map_tile_url: str = field(default_factory=lambda: _env("MAP_TILE_URL", ""))

    @property
    def is_dev(self) -> bool:
        return self.env in {"dev", "test", "local"}

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def validate(self) -> None:
        if not self.is_dev and self.jwt_secret.startswith("dev-only"):
            raise RuntimeError("JWT_SECRET must be set from the secret manager outside dev")
        if not self.is_dev and self.otp_debug_return:
            raise RuntimeError("OTP_DEBUG_RETURN must be 0 outside dev")


settings = Settings()
