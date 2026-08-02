"""
Integration tests for per-namespace agent rate limiting.

Tests verify that:
- Requests within the limit are allowed through
- Requests exceeding the limit receive HTTP 429
- Different namespaces have independent counters
- The counter resets after the time window expires
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
    """Create a mock Redis client returning the given counter value."""
    mock_redis = MagicMock()
    mock_redis.incr = AsyncMock(return_value=current_count)
    mock_redis.expire = AsyncMock(return_value=True)
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

    mock_redis.incr.assert_called_once_with("finbot:ratelimit:ns_test_001:agent")
    mock_redis.expire.assert_called_once()


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
        # Should not raise — count 10 == max 10, still allowed
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
async def test_different_namespaces_are_independent():
    """Two different namespaces should use separate Redis keys."""
    session_a = make_session_context("ns_aaa")
    session_b = make_session_context("ns_bbb")

    called_keys = []

    async def fake_incr(key):
        called_keys.append(key)
        return 1

    mock_redis = MagicMock()
    mock_redis.incr = fake_incr
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.ttl = AsyncMock(return_value=60)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_a)
        await check_agent_rate_limit(session_context=session_b)

    assert "finbot:ratelimit:ns_aaa:agent" in called_keys
    assert "finbot:ratelimit:ns_bbb:agent" in called_keys
    assert called_keys[0] != called_keys[1]


@pytest.mark.asyncio
async def test_expire_only_set_on_first_request():
    """Redis expire should only be called when count is 1 (first request in window)."""
    session_context = make_session_context("ns_test_006")
    mock_redis = make_mock_redis(current_count=5)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    # count is 5, not 1, so expire should NOT have been called
    mock_redis.expire.assert_not_called()


@pytest.mark.asyncio
async def test_expire_set_on_first_request():
    """Redis expire should be called when count is 1 (new window started)."""
    session_context = make_session_context("ns_test_007")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    mock_redis.expire.assert_called_once_with(
        "finbot:ratelimit:ns_test_007:agent", 60
    )


@pytest.mark.asyncio
async def test_redis_failure_allows_request_through():
    """If Redis is unavailable, the request should be allowed through (fail open)."""
    session_context = make_session_context("ns_test_008")

    mock_redis = MagicMock()
    mock_redis.incr = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        # Should NOT raise — fail open behavior
        await check_agent_rate_limit(session_context=session_context)


@pytest.mark.asyncio
async def test_redis_key_format():
    """The Redis key must follow the finbot:ratelimit:{namespace}:agent pattern."""
    session_context = make_session_context("ns_vendor_xyz")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    mock_redis.incr.assert_called_once_with(
        "finbot:ratelimit:ns_vendor_xyz:agent"
    )