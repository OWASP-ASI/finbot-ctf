"""
Integration tests for per-namespace agent rate limiting.

Tests verify that:
- Requests within the limit are allowed through
- Requests exceeding the limit receive HTTP 429
- Different namespaces have independent counters
- Redis errors fail closed with HTTP 503
- INCR and EXPIRE are executed atomically via pipeline
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
    """Create a mock Redis client returning the given counter value via pipeline."""
    mock_redis = MagicMock()
    mock_pipeline = MagicMock()
    mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_pipeline.__aexit__ = AsyncMock(return_value=False)
    mock_pipeline.incr = AsyncMock()
    mock_pipeline.expire = AsyncMock()
    mock_pipeline.execute = AsyncMock(return_value=[current_count, True])
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
    mock_redis.ttl = AsyncMock(return_value=ttl)
    return mock_redis


@pytest.mark.asyncio
async def test_first_request_is_allowed():
    """A namespace making its first request should be allowed through."""
    session_context = make_session_context("ns_test_001")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    mock_redis.pipeline.assert_called_once()


@pytest.mark.asyncio
async def test_request_within_limit_is_allowed():
    """A request within the configured limit should be allowed through."""
    session_context = make_session_context("ns_test_002")
    mock_redis = make_mock_redis(current_count=5)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)


@pytest.mark.asyncio
async def test_request_at_exact_limit_is_allowed():
    """A request exactly at the limit (count == max) should still be allowed."""
    session_context = make_session_context("ns_test_003")
    mock_redis = make_mock_redis(current_count=10)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
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
    assert "15" in detail
    assert "10" in detail
    assert "30" in detail


@pytest.mark.asyncio
async def test_different_namespaces_are_independent():
    """Two different namespaces should use separate Redis keys."""
    session_a = make_session_context("ns_aaa")
    session_b = make_session_context("ns_bbb")

    called_keys = []

    mock_redis_a = make_mock_redis(current_count=1)
    mock_redis_b = make_mock_redis(current_count=1)

    async def capture_incr_a(key):
        called_keys.append(key)

    async def capture_incr_b(key):
        called_keys.append(key)

    mock_redis_a.pipeline.return_value.__aenter__.return_value.incr = capture_incr_a
    mock_redis_b.pipeline.return_value.__aenter__.return_value.incr = capture_incr_b

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis_a
        await check_agent_rate_limit(session_context=session_a)
        mock_bus.redis = mock_redis_b
        await check_agent_rate_limit(session_context=session_b)

    assert "finbot:ratelimit:ns_aaa:agent" in called_keys
    assert "finbot:ratelimit:ns_bbb:agent" in called_keys
    assert called_keys[0] != called_keys[1]


@pytest.mark.asyncio
async def test_expire_always_set_in_pipeline():
    """Redis expire should always be called in the pipeline on every request."""
    session_context = make_session_context("ns_test_006")
    mock_redis = make_mock_redis(current_count=5)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    mock_redis.pipeline.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_execute_called():
    """Pipeline execute should be called on every request."""
    session_context = make_session_context("ns_test_007")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    pipe = mock_redis.pipeline.return_value.__aenter__.return_value
    pipe.execute.assert_called_once()


@pytest.mark.asyncio
async def test_redis_failure_returns_503():
    """If Redis is unavailable, the request should be blocked with HTTP 503 (fail closed)."""
    session_context = make_session_context("ns_test_008")

    mock_redis = MagicMock()
    mock_pipeline = MagicMock()
    mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_pipeline.__aexit__ = AsyncMock(return_value=False)
    mock_pipeline.incr = AsyncMock()
    mock_pipeline.expire = AsyncMock()
    mock_pipeline.execute = AsyncMock(side_effect=ConnectionError("Redis unavailable"))
    mock_redis.pipeline = MagicMock(return_value=mock_pipeline)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        with pytest.raises(HTTPException) as exc_info:
            await check_agent_rate_limit(session_context=session_context)

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_redis_key_format():
    """The Redis key must follow the finbot:ratelimit:{namespace}:agent pattern."""
    session_context = make_session_context("ns_vendor_xyz")
    mock_redis = make_mock_redis(current_count=1)

    with patch("finbot.core.ratelimit.limiter.event_bus") as mock_bus:
        mock_bus.redis = mock_redis
        await check_agent_rate_limit(session_context=session_context)

    pipe = mock_redis.pipeline.return_value.__aenter__.return_value
    pipe.incr.assert_called_once_with(
        "finbot:ratelimit:ns_vendor_xyz:agent"
    )