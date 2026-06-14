# ============================================================
# File: tests/unit/aegis/test_telemetry_chain.py
# Purpose: Unit tests for HMAC audit chain
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 2
# OWASP Category: ASI06 (Sandboxing)
# ============================================================
"""Tests for AEGIS telemetry HMAC chain and tamper detection."""

import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from finbot.aegis.telemetry.chain import AuditChain
from finbot.aegis.telemetry.schema import (
    ToolCallEvent,
    ToolResultEvent,
    PolicyDecisionEvent,
)


@pytest.mark.unit
class TestAuditChainHashComputation:
    """Test HMAC hash computation and chaining."""

    def test_hash_computation(self) -> None:
        """Compute HMAC-SHA256 correctly."""
        chain = AuditChain()
        prev_hash = ""
        event_json = '{"tool_name":"test"}'

        hash1 = chain._compute_hash(prev_hash, event_json)
        hash2 = chain._compute_hash(prev_hash, event_json)

        # Same input -> same hash
        assert hash1 == hash2

    def test_hash_changes_with_prev_hash(self) -> None:
        """Hash changes when prev_hash changes."""
        chain = AuditChain()
        event_json = '{"tool_name":"test"}'

        hash1 = chain._compute_hash("", event_json)
        hash2 = chain._compute_hash("abc123", event_json)

        # Different prev_hash -> different hash
        assert hash1 != hash2

    def test_hash_changes_with_event(self) -> None:
        """Hash changes when event JSON changes."""
        chain = AuditChain()
        prev_hash = "abc123"

        hash1 = chain._compute_hash(prev_hash, '{"tool":"tool1"}')
        hash2 = chain._compute_hash(prev_hash, '{"tool":"tool2"}')

        assert hash1 != hash2

    def test_hash_deterministic(self) -> None:
        """Same event always produces same hash."""
        chain = AuditChain()
        prev_hash = "abc123"
        event_json = '{"tool_name":"create_vendor","arguments":{"name":"Acme"}}'

        hashes = [chain._compute_hash(prev_hash, event_json) for _ in range(5)]

        # All hashes should be identical
        assert len(set(hashes)) == 1


@pytest.mark.unit
class TestCanonicalJsonSerialization:
    """Test canonical JSON serialization."""

    def test_canonical_json_sorted_keys(self) -> None:
        """Canonical JSON sorts keys."""
        chain = AuditChain()

        obj = {"z": 1, "a": 2, "m": 3}
        canonical = chain._canonical_json(obj)

        # Keys should be in order: a, m, z
        expected = '{"a":2,"m":3,"z":1}'
        assert canonical == expected

    def test_canonical_json_no_spaces(self) -> None:
        """Canonical JSON has no extra whitespace."""
        chain = AuditChain()

        obj = {"key": "value", "number": 42}
        canonical = chain._canonical_json(obj)

        assert " " not in canonical

    def test_canonical_json_nested(self) -> None:
        """Canonical JSON handles nested objects."""
        chain = AuditChain()

        obj = {"tool": {"name": "test", "source": "api"}, "id": 1}
        canonical = chain._canonical_json(obj)

        # Should be deterministic even with nesting
        assert canonical == chain._canonical_json(obj)


@pytest.mark.unit
@pytest.mark.asyncio
class TestAuditChainAppend:
    """Test appending events to the chain."""

    async def test_append_tool_call_event(self) -> None:
        """Append a ToolCallEvent to the chain."""
        chain = AuditChain()

        # Mock Redis connection
        mock_redis = AsyncMock()
        mock_redis.xrevrange.return_value = []  # No previous events
        mock_redis.xadd.return_value = b"1234567890000-0"

        chain._redis = mock_redis

        event = ToolCallEvent(
            namespace="player_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="create_vendor",
            tool_source="finstripe",
        )

        hash_val = await chain.append(event)

        # Should return a hash
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA256 hex digest length
        # Should have called Redis xadd
        assert mock_redis.xadd.called

    async def test_append_invalid_event_raises_error(self) -> None:
        """Appending non-event object raises ValueError."""
        chain = AuditChain()

        with pytest.raises(ValueError):
            await chain.append("not an event")  # type: ignore

    async def test_append_chain_linking(self) -> None:
        """Hash from first event becomes prev_hash of second event."""
        chain = AuditChain()

        mock_redis = AsyncMock()
        mock_redis.xrevrange.return_value = []
        mock_redis.xadd.return_value = b"1234567890000-0"

        chain._redis = mock_redis

        event1 = ToolCallEvent(
            namespace="player_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="tool1",
            tool_source="source1",
        )

        hash1 = await chain.append(event1)

        # Cache should have the hash
        assert chain._last_hash_cache.get("player_1") == hash1

        # Second event's prev_hash should be the first event's hash
        mock_redis.xrevrange.return_value = [
            (b"1234567890000-0", {b"event_hash": hash1.encode()})
        ]

        event2 = ToolCallEvent(
            namespace="player_1",
            workflow_id="wf_2",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="tool2",
            tool_source="source2",
        )

        hash2 = await chain.append(event2)

        # Hashes should be different (linked chain)
        assert hash1 != hash2


@pytest.mark.unit
@pytest.mark.asyncio
class TestAuditChainVerification:
    """Test audit chain verification for tamper detection."""

    async def test_verify_chain_valid(self) -> None:
        """Verification succeeds for untampered chain."""
        chain = AuditChain()

        # Create a simple chain of 2 events
        event1_dict = {
            "tool_name": "tool1",
            "timestamp": "2026-05-27T12:00:00Z",
        }
        event1_json = chain._canonical_json(event1_dict)
        hash1 = chain._compute_hash("", event1_json)

        event2_dict = {
            "tool_name": "tool2",
            "timestamp": "2026-05-27T12:01:00Z",
        }
        event2_json = chain._canonical_json(event2_dict)
        hash2 = chain._compute_hash(hash1, event2_json)

        # Mock Redis to return these events
        mock_redis = AsyncMock()
        mock_redis.xrange.return_value = [
            (b"1234567890000-0", {
                b"event_json": event1_json.encode(),
                b"event_hash": hash1.encode(),
                b"prev_hash": b"",
            }),
            (b"1234567890001-0", {
                b"event_json": event2_json.encode(),
                b"event_hash": hash2.encode(),
                b"prev_hash": hash1.encode(),
            }),
        ]

        chain._redis = mock_redis

        is_valid, message = await chain.verify_chain("player_1")

        assert is_valid is True
        assert "valid" in message.lower()

    async def test_verify_chain_tampered(self) -> None:
        """Verification fails if event was tampered with."""
        chain = AuditChain()

        # Create chain, but return wrong hash for second event
        event1_dict = {"tool_name": "tool1"}
        event1_json = chain._canonical_json(event1_dict)
        hash1 = chain._compute_hash("", event1_json)

        event2_dict = {"tool_name": "tool2"}
        event2_json = chain._canonical_json(event2_dict)
        # Compute correct hash
        correct_hash2 = chain._compute_hash(hash1, event2_json)
        # But store wrong hash (tampered)
        wrong_hash2 = "0000000000000000000000000000000000000000000000000000000000000000"

        mock_redis = AsyncMock()
        mock_redis.xrange.return_value = [
            (b"1234567890000-0", {
                b"event_json": event1_json.encode(),
                b"event_hash": hash1.encode(),
                b"prev_hash": b"",
            }),
            (b"1234567890001-0", {
                b"event_json": event2_json.encode(),
                b"event_hash": wrong_hash2.encode(),
                b"prev_hash": hash1.encode(),
            }),
        ]

        chain._redis = mock_redis

        is_valid, message = await chain.verify_chain("player_1")

        assert is_valid is False
        assert "tamper" in message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
class TestAuditChainRetrieval:
    """Test retrieving events from the chain."""

    async def test_get_chain_returns_events(self) -> None:
        """get_chain retrieves events from Redis."""
        chain = AuditChain()

        event_dict = {
            "@type": "aegis.tool.call",
            "tool_name": "test_tool",
            "timestamp": "2026-05-27T12:00:00Z",
        }
        event_json = chain._canonical_json(event_dict)

        mock_redis = AsyncMock()
        mock_redis.xrange.return_value = [
            (b"1234567890000-0", {
                b"event_json": event_json.encode(),
                b"event_hash": b"abc123",
            }),
        ]

        chain._redis = mock_redis

        events = await chain.get_chain("player_1")

        assert len(events) == 1
        assert events[0]["tool_name"] == "test_tool"
        assert events[0]["_stored_hash"] == "abc123"

    async def test_get_chain_pagination(self) -> None:
        """get_chain respects start and count parameters."""
        chain = AuditChain()

        # Create 5 events
        mock_entries = [
            (
                f"event_{i}".encode(),
                {
                    b"event_json": json.dumps({"index": i}).encode(),
                    b"event_hash": f"hash_{i}".encode(),
                },
            )
            for i in range(5)
        ]

        mock_redis = AsyncMock()
        mock_redis.xrange.return_value = mock_entries

        chain._redis = mock_redis

        # Get events 1-2 (start=1, count=2)
        events = await chain.get_chain("player_1", start=1, count=2)

        # Should return events at indices 1 and 2
        assert len(events) == 2


@pytest.mark.unit
@pytest.mark.asyncio
class TestAuditChainCleanup:
    """Test cleanup of old events."""

    async def test_cleanup_old_events(self) -> None:
        """cleanup_old_events removes events older than TTL."""
        chain = AuditChain()

        mock_redis = AsyncMock()
        mock_redis.xtrim.return_value = 5  # 5 events deleted

        chain._redis = mock_redis

        deleted = await chain.cleanup_old_events("player_1", retain_days=7)

        assert deleted == 5
        assert mock_redis.xtrim.called

    async def test_cleanup_handles_error(self) -> None:
        """cleanup_old_events handles Redis errors gracefully."""
        chain = AuditChain()

        mock_redis = AsyncMock()
        mock_redis.xtrim.side_effect = Exception("Redis error")

        chain._redis = mock_redis

        # Should return 0 on error, not raise
        deleted = await chain.cleanup_old_events("player_1", retain_days=7)

        assert deleted == 0
