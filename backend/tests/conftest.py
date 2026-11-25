"""Test fixtures: an isolated SQLite database, seeded, with a FastAPI test client.

The environment is set before `app` is imported, because settings are read at import.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "test_kumbh.db"
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ.setdefault("KUMBH_ENV", "test")
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
os.environ["OTP_DEBUG_RETURN"] = "1"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["KAFKA_BOOTSTRAP"] = ""
os.environ["OFFICER_MFA_REQUIRED"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import create_all  # noqa: E402
from app.main import app  # noqa: E402
from app.seeds.seed import seed  # noqa: E402


def totp(secret_b32: str, at: float | None = None) -> str:
    """Same RFC 6238 algorithm as the login endpoint, for the test client."""
    key = base64.b32decode(secret_b32.upper())
    counter = int((at or time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    index = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[index:index + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    create_all()
    seed()
    yield
    if DB_PATH.exists():
        DB_PATH.unlink()


@pytest.fixture(scope="session")
def client(seeded_database) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def visitor_token(client: TestClient, phone: str = "9876543210") -> str:
    requested = client.post("/v1/auth/otp/request", json={"phone": phone}).json()
    verified = client.post("/v1/auth/otp/verify", json={
        "request_id": requested["request_id"], "phone": phone, "otp": requested["dev_otp"],
    })
    assert verified.status_code == 200, verified.text
    return verified.json()["access_token"]


def officer_token(client: TestClient, employee_code: str, phone: str) -> str:
    requested = client.post("/v1/auth/otp/request", json={"phone": phone}).json()
    response = client.post("/v1/auth/officer/login", json={
        "employee_code": employee_code,
        "phone": phone,
        "otp": requested["dev_otp"],
        "totp": totp("JBSWY3DPEHPK3PXP"),
    })
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
