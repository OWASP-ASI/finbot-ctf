# ============================================================
# File: tests/unit/aegis/test_sentinel.py
# Purpose: SentinelStream hash-chain unit tests
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 2
# OWASP Category: ASI06 Memory Poisoning
# ============================================================
from unittest.mock import AsyncMock, MagicMock

import pytest

from finbot.aegis.sentinel import SentinelStream


@pytest.fixture()
def sentinel(monkeypatch):
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock()
    monkeypatch.setattr(
        "finbot.aegis.sentinel.event_bus",
        MagicMock(redis=mock_redis, emit_agent_event=AsyncMock()),
    )
    return SentinelStream(), mock_redis


@pytest.mark.asyncio
async def test_record_sets_chain_head(sentinel):
    stream, redis = sentinel
    session = MagicMock(namespace="ns_test", user_id="user1")
    audit = await stream.record(
        event_type="policy.before_tool",
        namespace="ns_test",
        workflow_id="wf1",
        agent_name="invoice",
        payload={"tool": "finstripe__list_charges"},
        session_context=session,
    )
    assert audit.event_hash is not None
    assert audit.prev_hash is None
    redis.set.assert_awaited()


@pytest.mark.asyncio
async def test_record_links_prev_hash(sentinel, monkeypatch):
    stream, redis = sentinel
    redis.get = AsyncMock(return_value=b"abc123")
    session = MagicMock(namespace="ns_test", user_id="user1")
    audit = await stream.record(
        event_type="policy.before_tool",
        namespace="ns_test",
        workflow_id="wf1",
        agent_name="invoice",
        payload={},
        session_context=session,
    )
    assert audit.prev_hash == "abc123"
