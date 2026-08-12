"""
Agent Rate Limiter

Provides per-namespace rate limiting for agent-triggering endpoints.
Uses a fixed-window counter stored in Redis, reusing the existing
EventBus Redis connection.

INCR and EXPIRE are executed atomically via a Lua script (EVAL), so
there is no window between the two operations where a crash could
leave a key with no TTL.

Design choice: fails OPEN if Redis is unavailable (allows the request
through rather than blocking it). This is deliberate - rate limiting
here is a soft quota guard on LLM usage, not a security/auth control,
so an availability outage in Redis should not take down agent
endpoints (chat, onboarding, invoices) entirely. See PR discussion on
#532 for the fail-open vs fail-closed trade-off.
"""
import logging

from fastapi import Depends, HTTPException

from finbot.config import settings
from finbot.core.messaging.events import event_bus
from finbot.core.auth.middleware import get_session_context
from finbot.core.auth.session import SessionContext

logger = logging.getLogger(__name__)

# Atomically increments the counter and sets the expiry only on the
# key's first increment in the window, in a single round trip. This
# removes the INCR/EXPIRE race entirely (no separate fallback check
# is needed, unlike a plain INCR + conditional EXPIRE).
_INCR_AND_EXPIRE_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


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
        # Explicitly guard Redis initialization
        redis = getattr(event_bus, "redis", None)
        if redis is None:
            logger.warning("Rate limiter: Redis not initialized, allowing request through")
            return

        # Atomic increment + conditional expiry via Lua script
        count = await redis.eval(_INCR_AND_EXPIRE_SCRIPT, 1, key, window_seconds)

        logger.debug(
            "Rate limit check: namespace=%s count=%d max=%d",
            namespace,
            count,
            max_requests,
        )

        if count > max_requests:
            # Get remaining TTL to report in the error message
            ttl = await redis.ttl(key)
            # Guard against negative TTL values (-1 = no expiry, -2 = key gone)
            if ttl < 0:
                ttl = window_seconds
            # Include Retry-After header in the 429 response
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
        # rather than blocking all users due to an infrastructure issue.
        # This is a deliberate fail-open design choice - see module
        # docstring for reasoning.
        logger.error("Rate limit check failed (Redis error): %s", e)