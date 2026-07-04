"""
Agent Rate Limiter
Provides per-namespace rate limiting for agent-triggering endpoints.
Uses a fixed-window counter stored in Redis, reusing the existing
EventBus Redis connection.
"""
import logging
from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from finbot.config import settings
from finbot.core.messaging.events import event_bus
from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext

logger = logging.getLogger(__name__)


async def check_agent_rate_limit(
    session_context: SessionContext = Depends(get_session_context),
) -> None:
    """FastAPI dependency that enforces per-namespace agent rate limiting.

    Raises HTTP 429 if the namespace has exceeded AGENT_RATE_LIMIT_MAX
    requests within the current AGENT_RATE_LIMIT_WINDOW_SECONDS window.

    Add to any route that triggers an agent or LLM call:
        Depends(check_agent_rate_limit)
    """
    namespace = session_context.namespace
    key = f"finbot:ratelimit:{namespace}:agent"
    max_requests = settings.AGENT_RATE_LIMIT_MAX
    window_seconds = settings.AGENT_RATE_LIMIT_WINDOW_SECONDS

    try:
        # Fix 2: Explicitly guard Redis initialization
        redis = getattr(event_bus, "redis", None)
        if redis is None:
            logger.warning("Rate limiter: Redis not initialized, allowing request through")
            return

        # Increment the counter for this namespace
        count = await redis.incr(key)

        # On the first request in a window, set the expiry
        if count == 1:
            await redis.expire(key, window_seconds)

        logger.debug(
            "Rate limit check: namespace=%s count=%d max=%d",
            namespace,
            count,
            max_requests,
        )

        if count > max_requests:
            # Get remaining TTL to report in the error message
            ttl = await redis.ttl(key)

            # Fix 3: Guard against negative TTL values (-1 = no expiry, -2 = key gone)
            if ttl < 0:
                ttl = window_seconds

            # Fix 1: Include Retry-After header in the 429 response
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Rate limit exceeded. You have sent {count} agent requests "
                    f"within the {window_seconds}s window (max {max_requests}). "
                    f"Please wait {ttl} seconds before trying again."
                ),
                headers={"Retry-After": str(ttl)},
            )

    except HTTPException:
        raise
    except Exception as e:
        # If Redis is unavailable, log and allow the request through
        # rather than blocking all users due to an infrastructure issue
        logger.error("Rate limit check failed (Redis error): %s", e)
