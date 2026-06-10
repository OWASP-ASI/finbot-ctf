"""Tests for agent tool call timeout.

Covers:
- Issue #201: Agent tool calls have no timeout, allowing indefinite blocking
"""

import asyncio

import pytest

from finbot.config import Settings


def test_agent_tool_timeout_setting_exists():
    """AGENT_TOOL_TIMEOUT setting should exist with a reasonable default."""
    s = Settings(DEBUG=True)
    assert hasattr(s, "AGENT_TOOL_TIMEOUT")
    assert s.AGENT_TOOL_TIMEOUT > 0


def test_agent_tool_timeout_default_value():
    """Default timeout should be 60 seconds."""
    s = Settings(DEBUG=True)
    assert s.AGENT_TOOL_TIMEOUT == 60


@pytest.mark.asyncio
async def test_wait_for_timeout_mechanism():
    """asyncio.wait_for should raise TimeoutError for slow tool calls."""

    async def slow_tool(**kwargs):
        await asyncio.sleep(10)
        return {"result": "should not reach"}

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_tool(), timeout=0.1)


@pytest.mark.asyncio
async def test_wait_for_allows_fast_calls():
    """asyncio.wait_for should not interfere with fast tool calls."""

    async def fast_tool(**kwargs):
        return {"result": "success"}

    result = await asyncio.wait_for(fast_tool(), timeout=5)
    assert result == {"result": "success"}
