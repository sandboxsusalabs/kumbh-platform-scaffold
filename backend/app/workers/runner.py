"""Background worker entry point.

Consumers that keep the platform honest under load:

    sos.priority    assign the nearest available team, escalate on timeout
    alert.broadcast fan out to push, SMS and public address; update delivery counters
    crowd.telemetry fold CCTV / gate-counter readings into the zone table
    incident.report mirror incidents into the ops WebSocket

Run:  python -m app.workers.runner            (all consumers)
      python -m app.workers.runner sos        (one topic, for debugging)

Without KAFKA_BOOTSTRAP the runner idles with a clear message instead of crashing, so
`docker compose up worker` is safe in a dev stack with no broker.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings
from app.services.events import (
    TOPIC_ALERT,
    TOPIC_CROWD,
    TOPIC_INCIDENT,
    TOPIC_SOS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("worker")

TOPICS = {
    TOPIC_SOS: "sos",
    TOPIC_ALERT: "alerts",
    TOPIC_CROWD: "crowd",
    TOPIC_INCIDENT: "incidents",
}


async def handle_sos(payload: dict) -> None:
    """Dispatch is created by the API; the worker escalates if nobody acknowledges."""
    log.info("SOS %s category=%s zone=%s priority=%s",
             payload.get("reference"), payload.get("category"),
             payload.get("zone_code"), payload.get("priority"))
    # TODO: pick the nearest available team from live team locations (Redis geo set),
    # then reassign the task and page the zone supervisor if unacknowledged in 60 s.


async def handle_alert(payload: dict) -> None:
    log.info("alert %s kind=%s channels=%s zones=%s", payload.get("alert_id"),
             payload.get("kind"), payload.get("channels"), payload.get("zones"))
    # TODO: batch push (FCM), SMS through the state gateway, PA via the control room
    # bridge; write sent/failed counts back to alert_deliveries.


async def handle_crowd(payload: dict) -> None:
    log.info("crowd %s level=%s ratio=%s", payload.get("zone_code"),
             payload.get("level"), payload.get("occupancy_ratio"))
    # TODO: merge CCTV + gate + network signals per zone before writing the level,
    # so one faulty camera cannot turn a ghat red.


async def handle_incident(payload: dict) -> None:
    log.info("incident %s kind=%s severity=%s zone=%s", payload.get("reference"),
             payload.get("kind"), payload.get("severity"), payload.get("zone_code"))


HANDLERS = {
    TOPIC_SOS: handle_sos,
    TOPIC_ALERT: handle_alert,
    TOPIC_CROWD: handle_crowd,
    TOPIC_INCIDENT: handle_incident,
}


async def consume(topic: str) -> None:
    from aiokafka import AIOKafkaConsumer

    group = f"kumbh-{TOPICS.get(topic, 'misc')}"
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id=group,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    log.info("consuming %s as %s", topic, group)
    try:
        async for message in consumer:
            try:
                payload = json.loads(message.value.decode())
            except json.JSONDecodeError:
                log.warning("dropping non-JSON message on %s", topic)
                continue
            handler = HANDLERS.get(topic)
            if handler:
                try:
                    await handler(payload)
                except Exception:  # noqa: BLE001 - one bad message must not stop the consumer
                    log.exception("handler failed for %s", topic)
    finally:
        await consumer.stop()


async def main() -> None:
    if not settings.kafka_bootstrap:
        log.warning("KAFKA_BOOTSTRAP is empty: worker started with nothing to consume. "
                    "Set it to the broker address to enable consumers.")
        while True:
            await asyncio.sleep(60)

    wanted = sys.argv[1:] or list(TOPICS)
    topics = [topic for topic in TOPICS if topic.split(".")[0] in wanted or TOPICS[topic] in wanted] or list(TOPICS)
    log.info("worker starting at %s for %s", datetime.now(timezone.utc).isoformat(), topics)
    await asyncio.gather(*[consume(topic) for topic in topics])


if __name__ == "__main__":  # pragma: no cover
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("worker stopped")
