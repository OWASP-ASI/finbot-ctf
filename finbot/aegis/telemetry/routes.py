# ============================================================
# File: finbot/aegis/telemetry/routes.py
# Purpose: FastAPI SSE endpoint for real-time telemetry dashboard
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 3
# OWASP Category: ASI01 (Prompt Injection), ASI10 (Insufficient Monitoring)
# ============================================================
"""FastAPI routes for AEGIS telemetry observability.

Exposes:
- GET /aegis/stream: Server-Sent Events (SSE) endpoint for real-time audit events
- GET /aegis/chain/{namespace}: Retrieve historical audit chain
- POST /aegis/verify: Verify audit chain integrity
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from finbot.config import settings
from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.aegis.telemetry.chain import AuditChain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/aegis", tags=["aegis-telemetry"])


def _get_audit_chain() -> AuditChain:
    """Dependency: get AuditChain instance."""
    return AuditChain()


async def _get_redis() -> Redis:
    """Dependency: get Redis connection."""
    return await Redis.from_url(settings.REDIS_URL)


@router.get("/stream", summary="Real-time Audit Event Stream (SSE)")
async def stream_audit_events(
    session: SessionContext = Depends(get_session_context),
    redis_client: Redis = Depends(_get_redis),
) -> StreamingResponse:
    """Stream real-time audit events via Server-Sent Events (SSE).

    Emits audit events (tool calls, policy decisions, anomalies) as they occur.
    Subscribe on client with:

    ```javascript
    const eventSource = new EventSource('/aegis/stream');
    eventSource.addEventListener('tool_call', (e) => {
        const event = JSON.parse(e.data);
        console.log('Tool called:', event.tool_name);
    });
    ```

    Returns:
        StreamingResponse with SSE MIME type (text/event-stream)
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generate SSE events from Redis Streams."""
        chain = AuditChain(redis_client)
        stream_name = "finbot:aegis:audit"
        last_id = "0"  # Start from beginning on connection
        namespace = session.namespace

        logger.info("SSE stream opened for namespace=%s", namespace)

        try:
            while True:
                # Read new events from Redis Stream
                # Set count=10 to batch read; timeout=100ms to avoid blocking
                try:
                    events = await redis_client.xread(
                        {stream_name: last_id},
                        count=10,
                        block=100,  # milliseconds
                    )

                    if not events:
                        # Timeout; send heartbeat comment to keep connection alive
                        yield ": heartbeat\n\n"
                        await asyncio.sleep(0.1)
                        continue

                    for stream, message_list in events:
                        for message_id, data in message_list:
                            # Only emit events for this namespace
                            event_namespace = data.get(b"namespace", b"").decode()
                            if event_namespace != namespace:
                                continue

                            try:
                                event_type = data.get(b"event_type", b"unknown").decode()
                                event_json_str = data.get(b"event_json", b"{}").decode()
                                event_dict = json.loads(event_json_str)

                                # Emit as SSE event with event type
                                yield f"event: {event_type}\n"
                                yield f"data: {json.dumps(event_dict)}\n\n"

                                last_id = message_id

                            except json.JSONDecodeError as e:
                                logger.warning(
                                    "Failed to parse event JSON: %s",
                                    e,
                                )
                                continue

                except asyncio.TimeoutError:
                    # Heartbeat already sent above
                    pass

        except asyncio.CancelledError:
            logger.info("SSE stream closed for namespace=%s", namespace)
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Error in SSE event generator: %s",
                e,
                exc_info=True,
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable proxy buffering
        },
    )


@router.get(
    "/chain/{namespace}",
    summary="Retrieve Historical Audit Chain",
)
async def get_audit_chain(
    namespace: str = Path(..., description="Player namespace"),
    start: int = Query(0, ge=0, description="Starting offset"),
    count: int = Query(100, ge=1, le=1000, description="Max events to return"),
    session: SessionContext = Depends(get_session_context),
    chain: AuditChain = Depends(_get_audit_chain),
) -> dict[str, Any]:
    """Retrieve historical audit events for a namespace.

    Args:
        namespace: Namespace to retrieve (must match player's namespace)
        start: Starting offset in event stream (0 = oldest)
        count: Max events to return (max 1000)

    Returns:
        {
            "namespace": str,
            "total_events": int,
            "events": [
                {
                    "@type": "aegis.tool.call",
                    "tool_name": "...",
                    "timestamp": "2026-05-27T...",
                    "event_hash": "...",
                    ...
                },
                ...
            ],
            "is_valid": bool,
            "validation_message": str
        }
    """
    # Enforce namespace isolation: only retrieve own namespace
    if session.namespace != namespace:
        raise HTTPException(
            status_code=403,
            detail="Cannot access another player's audit chain",
        )

    try:
        # Get events from chain
        events = await chain.get_chain(namespace, start=start, count=count)

        # Verify chain integrity
        is_valid, validation_msg = await chain.verify_chain(namespace)

        return {
            "namespace": namespace,
            "total_events": len(events),
            "start_offset": start,
            "events": events,
            "is_valid": is_valid,
            "validation_message": validation_msg,
        }
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Failed to retrieve audit chain for namespace=%s: %s",
            namespace,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve audit chain")


@router.post(
    "/verify",
    summary="Verify Audit Chain Integrity",
)
async def verify_chain(
    session: SessionContext = Depends(get_session_context),
    chain: AuditChain = Depends(_get_audit_chain),
) -> dict[str, Any]:
    """Verify the integrity of the audit chain for the current namespace.

    Walks the chain from oldest to newest event, recomputing HMAC hashes.
    Returns whether the chain has been tampered with.

    Returns:
        {
            "namespace": str,
            "is_valid": bool,
            "message": str,
            "verified_at": str (ISO 8601 timestamp)
        }
    """
    try:
        is_valid, message = await chain.verify_chain(session.namespace)

        return {
            "namespace": session.namespace,
            "is_valid": is_valid,
            "message": message,
            "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Failed to verify audit chain: %s",
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to verify audit chain")


# Import datetime at the end to avoid circular imports
from datetime import UTC, datetime
