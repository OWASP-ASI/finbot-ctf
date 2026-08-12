"""
Integration tests for per-namespace agent rate limiting.

Tests verify that:
- Requests within the limit are allowed through
- Requests exceeding the limit receive HTTP 429
- Different namespaces have independent counters
- INCR and expiry are applied atomically via a single Lua script call
- The limiter fails open if Redis is unavailable
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from finbot.core.ratelimit.limiter import check_agent_rate_limit
from finbot.core.auth.session import SessionContext
from datetime import datetime, UTC


def make_session_context(namespace: str) -> SessionContext:
    """Create a minimal SessionContext for testing with the given namespace."""
    return SessionContext(
        session_id="test-session-id",
        user_id="test-user-id",
        is_temporary=True,
        namespace=namespace,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC),
    )


def make_mock_redis(current_count: int, ttl: int = 30):
    """Create a mock Redis client whose eval() (the atomic INCR+EXPIRE
    Lua script) returns the given counter value."""
    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(return_value=current_count)
    mock_redis.ttl = AsyncMock(return_value=ttl)
    return mock_redis


@pytest.mark.asyncio
async def test_first_request_is_allowed():
    """A namespace making its first request should be allowed through."""
    session_context = make_session_context("ns_test_001")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        # Should not raise
        await check_agent_rate_limit(session_context=session_context)

    mock_redis.eval.assert_called_once()
    args = mock_redis.eval.call_args[0]
    assert args[2] == "finbot:ratelimit:ns_test_001:agent"


@pytest.mark.asyncio
async def test_request_within_limit_is_allowed():
    """A request within the configured limit should be allowed through."""
    session_context = make_session_context("ns_test_002")
    mock_redis = make_mock_redis(current_count=5)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        # Should not raise
        await check_agent_rate_limit(session_context=session_context)


@pytest.mark.asyncio
async def test_request_at_exact_limit_is_allowed():
    """A request exactly at the limit (count == max) should still be allowed."""
    session_context = make_session_context("ns_test_003")
    mock_redis = make_mock_redis(current_count=10)  # default max is 10

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        # Should not raise - count 10 == max 10, still allowed
        await check_agent_rate_limit(session_context=session_context)


@pytest.mark.asyncio
async def test_request_exceeding_limit_raises_429():
    """A request over the limit should raise HTTP 429."""
    session_context = make_session_context("ns_test_004")
    mock_redis = make_mock_redis(current_count=11, ttl=45)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        with pytest.raises(HTTPException) as exc_info:
            await check_agent_rate_limit(session_context=session_context)

    assert exc_info.value.status_code == 429
    assert "45" in exc_info.value.detail
    assert exc_info.value.headers.get("Retry-After") == "45"


@pytest.mark.asyncio
async def test_429_detail_contains_useful_info():
    """The 429 error detail should mention count, max, and wait time."""
    session_context = make_session_context("ns_test_005")
    mock_redis = make_mock_redis(current_count=15, ttl=30)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        with pytest.raises(HTTPException) as exc_info:
            await check_agent_rate_limit(session_context=session_context)

    detail = exc_info.value.detail
    assert "15" in detail   # current count
    assert "10" in detail   # max requests
    assert "30" in detail   # ttl / wait time


@pytest.mark.asyncio
async def test_negative_ttl_falls_back_to_window_seconds():
    """If Redis returns a negative TTL (-1 or -2), the reported wait
    time should fall back to the configured window length instead of
    showing a confusing negative number."""
    session_context = make_session_context("ns_test_009")
    mock_redis = make_mock_redis(current_count=12, ttl=-1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        with pytest.raises(HTTPException) as exc_info:
            await check_agent_rate_limit(session_context=session_context)

    assert "60" in exc_info.value.detail  # falls back to window_seconds
    assert exc_info.value.headers.get("Retry-After") == "60"


@pytest.mark.asyncio
async def test_different_namespaces_are_independent():
    """Two different namespaces should use separate Redis keys."""
    session_a = make_session_context("ns_aaa")
    session_b = make_session_context("ns_bbb")

    called_keys = []

    async def fake_eval(script, numkeys, key, *args):
        called_keys.append(key)
        return 1

    mock_redis = MagicMock()
    mock_redis.eval = fake_eval
    mock_redis.ttl = AsyncMock(return_value=60)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_a)
        await check_agent_rate_limit(session_context=session_b)

    assert "finbot:ratelimit:ns_aaa:agent" in called_keys
    assert "finbot:ratelimit:ns_bbb:agent" in called_keys
    assert called_keys[0] != called_keys[1]


@pytest.mark.asyncio
async def test_incr_and_expire_are_atomic_via_single_eval_call():
    """INCR and EXPIRE must happen atomically in one Lua script call
    (not as two separate round trips), so there is no window where a
    crash could leave a key incremented but without a TTL."""
    session_context = make_session_context("ns_test_006")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    # Exactly one Redis round trip for the increment+expire, every time,
    # regardless of whether this is the first request in the window.
    mock_redis.eval.assert_called_once()
    args = mock_redis.eval.call_args[0]
    assert args[1] == 1  # numkeys
    assert args[2] == "finbot:ratelimit:ns_test_006:agent"
    assert args[3] == 60  # window_seconds passed as ARGV[1]


@pytest.mark.asyncio
async def test_redis_failure_allows_request_through():
    """If Redis is unavailable, the request should be allowed through
    (fail open). This is a deliberate design choice: rate limiting is
    a soft quota guard, not an auth/security control, so a Redis outage
    should not take down agent endpoints entirely."""
    session_context = make_session_context("ns_test_008")

    mock_redis = MagicMock()
    mock_redis.eval = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        # Should NOT raise - fail open behavior
        await check_agent_rate_limit(session_context=session_context)


@pytest.mark.asyncio
async def test_redis_key_format():
    """The Redis key must follow the finbot:ratelimit:{namespace}:agent pattern."""
    session_context = make_session_context("ns_vendor_xyz")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    args = mock_redis.eval.call_args[0]
    assert args[2] == "finbot:ratelimit:ns_vendor_xyz:agent"