"""Event bus.

The API never blocks on Kafka: a publish failure is logged and the request still
succeeds, because the database write already happened (SOS is durable before it is
queued). When `KAFKA_BOOTSTRAP` is empty — local dev and tests — publishes are no-ops
and are recorded in an in-memory list so tests can assert on them.

Topics:
    sos.priority      SOS events, highest-priority consumer group
    incident.report   field incidents
    crowd.telemetry   CCTV / gate-counter readings
    alert.broadcast   alert fan-out to push, SMS and PA
    facility.status   facility status changes for the visitor map
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.core.config import settings

log = logging.getLogger(__name__)

TOPIC_SOS = "sos.priority"
TOPIC_INCIDENT = "incident.report"
TOPIC_CROWD = "crowd.telemetry"
TOPIC_ALERT = "alert.broadcast"
TOPIC_FACILITY = "facility.status"

PUBLISHED: List[Dict[str, Any]] = []  # dev/test audit trail


def _serialise(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, default=str, separators=(",", ":")).encode()


async def publish(topic: str, key: str, payload: Dict[str, Any]) -> None:
    """Fire-and-forget publish. Never raises into the request path."""
    if not settings.kafka_bootstrap:
        PUBLISHED.append({"topic": topic, "key": key, "payload": payload})
        log.debug("kafka disabled, recorded %s/%s", topic, key)
        return
    try:
        from aiokafka import AIOKafkaProducer  # imported lazily: optional dependency

        producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap, acks="all")
        await producer.start()
        try:
            await producer.send_and_wait(topic, _serialise(payload), key=key.encode())
        finally:
            await producer.stop()
    except Exception as exc:  # noqa: BLE001 - bus must never break the API
        log.warning("kafka publish failed topic=%s key=%s err=%s", topic, key, exc)
        PUBLISHED.append({"topic": topic, "key": key, "payload": payload, "failed": str(exc)})


def publish_sync(topic: str, key: str, payload: Dict[str, Any]) -> None:
    """For sync endpoints: schedule the coroutine without awaiting it.

    FastAPI runs sync endpoints in a threadpool with no running loop, so we use
    `asyncio.run` there and fall back to the dev recorder if that is unavailable.
    """
    import asyncio

    try:
        asyncio.run(publish(topic, key, payload))
    except RuntimeError:
        PUBLISHED.append({"topic": topic, "key": key, "payload": payload})
