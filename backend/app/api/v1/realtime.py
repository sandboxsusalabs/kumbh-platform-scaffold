"""Live surfaces: SSE for visitors, WebSocket for the common operating picture.

SSE is used for the visitor app because it survives weak networks and proxies better
than a WebSocket, and it reconnects on its own. The dashboard gets a WebSocket because
it needs to send as well as receive.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.core.security import Principal, TokenError, decode_token
from app.services.realtime import CHANNEL_ALERTS, CHANNEL_OPS, broker, sse_frame

router = APIRouter(tags=["realtime"])

HEARTBEAT_SECONDS = 20


@router.get("/stream/alerts", summary="SSE: alerts as they are broadcast")
async def alert_stream(request: Request, token: str = Query(description="Bearer JWT")):
    try:
        decode_token(token)
    except TokenError as exc:
        return StreamingResponse(
            iter([sse_frame("error", {"detail": str(exc)})]),
            media_type="text/event-stream",
            status_code=401,
        )

    queue = await broker.subscribe(CHANNEL_ALERTS)

    async def event_source():
        try:
            yield sse_frame("hello", {"at": datetime.now(timezone.utc).isoformat(),
                                     "channel": CHANNEL_ALERTS})
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                    yield sse_frame(message.get("type", "message"), message)
                except asyncio.TimeoutError:
                    yield sse_frame("ping", {"at": datetime.now(timezone.utc).isoformat()})
        finally:
            await broker.unsubscribe(CHANNEL_ALERTS, queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.websocket("/ws/ops")
async def ops_socket(websocket: WebSocket, token: str = Query(default="")):
    """Common operating picture: SOS, incidents, zone density, task states."""
    try:
        principal: Principal = decode_token(token)
    except TokenError:
        await websocket.close(code=4401)
        return
    if not principal.is_official:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    queue = await broker.subscribe(CHANNEL_OPS)
    await websocket.send_json({"type": "hello", "role": principal.role,
                               "agency": principal.agency, "zone": principal.zone})

    async def pump():
        while True:
            message = await queue.get()
            await websocket.send_json(message)

    pump_task = asyncio.create_task(pump())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        await broker.unsubscribe(CHANNEL_OPS, queue)


@router.get("/stream/stats", summary="Connected live clients (debug)")
def stats() -> dict:
    return {"subscribers": broker.subscriber_count,
            "at": datetime.now(timezone.utc).isoformat()}
