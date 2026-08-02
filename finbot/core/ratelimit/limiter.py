"""
Agent Rate Limiter

Provides per-namespace rate limiting for agent-triggering endpoints.
Uses an atomic Redis pipeline to increment and set expiry in a single
operation, preventing race conditions between INCR and EXPIRE.
Fails closed on Redis errors to prevent abuse during outages.
"""

import logging

from fastapi import Depends, HTTPException

from finbot.config import settings
from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext
from finbot.core.messaging.events import event_bus

logger = logging.getLogger(__name__)


async def check_agent_rate_limit(
    session_context: SessionContext = Depends(get_session_context),
) -> None:
    """FastAPI dependency that enforces per-namespace agent rate limiting.

    Uses an atomic Redis pipeline so INCR and EXPIRE are never split.
    Fails closed with HTTP 503 if Redis is unavailable, to prevent
    abuse during outages.

    Raises HTTP 429 if the namespace has exceeded AGENT_RATE_LIMIT_MAX
    requests within the current AGENT_RATE_LIMIT_WINDOW_SECONDS window.
    """
    namespace = session_context.namespace
    key = f"finbot:ratelimit:{namespace}:agent"
    max_requests = settings.AGENT_RATE_LIMIT_MAX
    window_seconds = settings.AGENT_RATE_LIMIT_WINDOW_SECONDS

    try:
        redis = getattr(event_bus, "redis", None)
        if redis is None:
            raise RuntimeError("Redis client is not initialized")

        # Atomic pipeline: INCR and EXPIRE in a single round trip
        # This prevents the race condition where INCR succeeds but
        # EXPIRE never runs, leaving a permanent key with no TTL
        async with redis.pipeline(transaction=True) as pipe:
            await pipe.incr(key)
            await pipe.expire(key, window_seconds)
            results = await pipe.execute()

        count = results[0]

        logger.debug(
            "Rate limit check: namespace=%s count=%d max=%d",
            namespace,
            count,
            max_requests,
        )

        if count > max_requests:
            ttl = await redis.ttl(key)
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded. You have sent {count} agent requests "
                    f"within the {window_seconds}s window (max {max_requests}). "
                    f"Please wait {ttl} seconds before trying again."
                ),
            )

    except HTTPException:
        raise

    except Exception as e:
        # Fail closed: if Redis is unavailable or any error occurs,
        # block the request rather than allowing potential abuse
        logger.error("Rate limit check failed, blocking request: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Rate limiting service unavailable. Please try again shortly.",
        )