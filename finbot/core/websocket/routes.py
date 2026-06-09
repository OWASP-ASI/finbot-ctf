"""WebSocket Endpoints"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from finbot.config import settings
from finbot.core.websocket.events import WSEvent, WSEventType
from finbot.core.websocket.manager import get_ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])


@router.get("/health")
async def ws_health():
    """Health check for websocket router"""
    return {"status": "ok", "router": "websocket"}


class TestEventRequest(BaseModel):
    """Request body for pushing a test event."""

    namespace: str
    user_id: str
    event_type: str
    data: dict = {}


@router.post("/test/push")
async def push_test_event(req: TestEventRequest):
    """Push a test event to a user's WebSocket connections. DEBUG only."""
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    manager = get_ws_manager()
    count = manager.get_user_connection_count(req.namespace, req.user_id)
    if count == 0:
        return {"sent": False, "reason": "no active connections", "connections": 0}

    try:
        event_type = WSEventType(req.event_type)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event type: {req.event_type}. "
            f"Valid: {[e.value for e in WSEventType]}",
        ) from exc

    event = WSEvent(type=event_type, data=req.data)
    await manager.send_to_user(req.namespace, req.user_id, event)
    return {"sent": True, "connections": count, "event_type": req.event_type}


@router.websocket("/connect")
async def websocket_endpoint(
    websocket: WebSocket,
    namespace: str = Query(...),
    user_id: str = Query(...),
):
    """
    WebSocket endpoint for real-time updates.

    Query params:
    - namespace: User's namespace
    - user_id: User's ID

    Message format (JSON):
    - {"action": "subscribe", "topic": "..."}
    - {"action": "unsubscribe", "topic": "..."}
    - {"action": "ping"}
    """
    manager = get_ws_manager()
    connection_id = await manager.connect(websocket, user_id, namespace)

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "subscribe":
                    topic = message.get("topic")
                    if topic:
                        await manager.subscribe(connection_id, topic)

                elif action == "unsubscribe":
                    topic = message.get("topic")
                    if topic:
                        await manager.unsubscribe(connection_id, topic)

                elif action == "ping":
                    await manager.send_to_connection(connection_id, WSEvent(type=WSEventType.PONG))

                else:
                    await manager.send_to_connection(
                        connection_id,
                        WSEvent(
                            type=WSEventType.ERROR,
                            data={"message": f"Unknown action: {action}"},
                        ),
                    )

            except json.JSONDecodeError:
                await manager.send_to_connection(
                    connection_id,
                    WSEvent(type=WSEventType.ERROR, data={"message": "Invalid JSON"}),
                )

    except WebSocketDisconnect:
        await manager.disconnect(connection_id)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("WebSocket error: %s", e)
        await manager.disconnect(connection_id)
