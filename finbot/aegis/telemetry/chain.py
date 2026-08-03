# ============================================================
# File: finbot/aegis/telemetry/chain.py
# Purpose: HMAC-SHA256 chaining + Redis Streams publisher
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 2
# OWASP Category: ASI06 (Sandboxing), ASI01 (Prompt Injection)
# ============================================================
"""HMAC-based immutable audit chain for tamper detection.

Implements cryptographic chaining where each event's hash depends on
the previous event's hash, making it impossible to silently modify
an event without invalidating all subsequent events.
"""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any, Optional

import redis.asyncio as redis

from finbot.config import settings
from finbot.aegis.telemetry.schema import (
    BaseAuditEvent,
    ToolCallEvent,
    ToolResultEvent,
    MemoryWriteEvent,
    DelegationEvent,
    PolicyDecisionEvent,
    AnomalyDetectionEvent,
)

logger = logging.getLogger(__name__)


class AuditChain:
    """HMAC-SHA256 immutable audit chain backed by Redis Streams.

    For each event:
    1. Serialize to canonical JSON (sorted keys, deterministic)
    2. Compute HMAC-SHA256(prev_hash || event_json, CHAIN_SECRET)
    3. Store event + hash in Redis Stream
    4. Return hash for next event to link

    Validates: If any event is tampered with, all subsequent hashes become invalid.
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """Initialize audit chain.

        Args:
            redis_client: Redis async client (defaults to settings.REDIS_URL)
        """
        self._redis = redis_client
        secret = getattr(settings, "AEGIS_CHAIN_SECRET", None)
        if not secret:
            raise RuntimeError(
                "AEGIS_CHAIN_SECRET must be configured."
            )
        self._chain_secret = secret
        self._stream_name = "finbot:aegis:audit"
        self._last_hash_cache: dict[str, str] = {}  # namespace -> last_hash

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = await redis.from_url(settings.REDIS_URL)
        return self._redis

    @staticmethod
    def _canonical_json(obj: dict[str, Any]) -> str:
        """Serialize to canonical JSON: sorted keys, no spaces."""
        return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)

    def _compute_hash(self, prev_hash: str, event_json: str) -> str:
        """Compute HMAC-SHA256(prev_hash || event_json, secret).

        Args:
            prev_hash: Hash of previous event (or empty string for first event)
            event_json: Canonical JSON of current event

        Returns:
            HMAC-SHA256 digest as hex string
        """
        message = (prev_hash + event_json).encode()
        signature = hmac.new(
            self._chain_secret.encode(),
            message,
            hashlib.sha256,
        )
        return signature.hexdigest()

    async def append(
        self,
        event: (
            ToolCallEvent
            | ToolResultEvent
            | MemoryWriteEvent
            | DelegationEvent
            | PolicyDecisionEvent
            | AnomalyDetectionEvent
        ),
    ) -> str:
        """Append event to audit chain; return its hash.

        Args:
            event: Audit event to append

        Returns:
            HMAC-SHA256 hash of this event

        Raises:
            ValueError: If event validation fails
            redis.ConnectionError: If Redis is unavailable
        """
        # Validate event
        if not isinstance(event, BaseAuditEvent):
            raise ValueError(f"Invalid event type: {type(event)}")

        # Serialize to dict for JSON encoding
        event_dict = event.model_dump(by_alias=True, exclude_none=False)
        event_json = self._canonical_json(event_dict)

        # Get previous hash from cache or Redis
        namespace = event.namespace
        prev_hash = self._last_hash_cache.get(namespace, "")
        if not prev_hash:
            # Retrieve last hash from Redis for this namespace
            r = await self._get_redis()
            try:
                last_entry = await r.xrevrange(
                    self._stream_name,
                    count=1,
                    filters={"namespace": namespace.encode()},
                )
                if last_entry:
                    prev_hash = last_entry[0][1].get(b"event_hash", b"").decode()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Failed to retrieve last hash from Redis for namespace=%s: %s",
                    namespace,
                    e,
                )
                prev_hash = ""

        # Compute hash for this event
        event_hash = self._compute_hash(prev_hash, event_json)

        # Update event with hash and prev_hash
        event_dict["event_hash"] = event_hash
        event_dict["prev_hash"] = prev_hash if prev_hash else None

        # Store in Redis Stream
        r = await self._get_redis()
        try:
            entry_id = await r.xadd(
                self._stream_name,
                {
                    "namespace": namespace,
                    "workflow_id": event.workflow_id,
                    "event_type": event_dict.get("@type", "unknown"),
                    "event_json": event_json,
                    "event_hash": event_hash,
                    "prev_hash": prev_hash or "",
                    "timestamp": event.timestamp,
                },
            )
            logger.debug(
                "Appended audit event: entry_id=%s, hash=%s, namespace=%s",
                entry_id,
                event_hash[:16],
                namespace,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Failed to append audit event to Redis: %s",
                e,
                exc_info=True,
            )
            raise

        # Cache the hash for next event in this namespace
        self._last_hash_cache[namespace] = event_hash

        return event_hash

    async def verify_chain(self, namespace: str) -> tuple[bool, str]:
        """Verify integrity of audit chain for a namespace.

        Walks the chain from oldest to newest, recomputing each hash.
        If any hash doesn't match, the chain is tampered.

        Args:
            namespace: Namespace to verify

        Returns:
            (is_valid, message): Tuple of (bool, str) describing result
        """
        r = await self._get_redis()
        try:
            entries = await r.xrange(
                self._stream_name,
                filters={"namespace": namespace.encode()},
            )
        except Exception as e:  # noqa: BLE001
            return False, f"Failed to read audit chain: {e}"

        if not entries:
            return True, "Empty chain (nothing to verify)"

        prev_hash = ""
        for entry_id, data in entries:
            stored_event_hash = data.get(b"event_hash", b"").decode()
            stored_prev_hash = data.get(b"prev_hash", b"").decode()
            event_json = data.get(b"event_json", b"").decode()

            # Recompute hash
            computed_hash = self._compute_hash(stored_prev_hash, event_json)

            if computed_hash != stored_event_hash:
                return (
                    False,
                    f"Tamper detected at entry {entry_id}: "
                    f"expected {stored_event_hash}, got {computed_hash}",
                )

            prev_hash = stored_event_hash

        return True, f"Chain valid ({len(entries)} events)"

    async def get_chain(self, namespace: str, start: int = 0, count: int = 100) -> list[dict[str, Any]]:
        """Retrieve audit chain events for a namespace.

        Args:
            namespace: Namespace to retrieve
            start: Starting offset (0 = oldest)
            count: Max events to return

        Returns:
            List of events (parsed from JSON, with hashes)
        """
        r = await self._get_redis()
        try:
            entries = await r.xrange(
                self._stream_name,
                filters={"namespace": namespace.encode()},
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to retrieve audit chain: %s", e)
            return []

        events = []
        for entry_id, data in entries[start : start + count]:
            try:
                event_json_str = data.get(b"event_json", b"").decode()
                event_dict = json.loads(event_json_str)
                event_dict["_entry_id"] = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                event_dict["_stored_hash"] = data.get(b"event_hash", b"").decode()
                events.append(event_dict)
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Failed to parse event from audit chain: %s",
                    e,
                )
                continue

        return events

    async def cleanup_old_events(self, namespace: str, retain_days: int = 7) -> int:
        """Remove audit events older than retain_days.

        Args:
            namespace: Namespace to clean
            retain_days: Keep events newer than this many days

        Returns:
            Number of events deleted
        """
        from datetime import timedelta

        r = await self._get_redis()
        cutoff = datetime.now(UTC) - timedelta(days=retain_days)
        cutoff_ms = int(cutoff.timestamp() * 1000)

        try:
            # XTRIM is the preferred way to clean streams
            deleted = await r.xtrim(
                self._stream_name,
                minid=cutoff_ms,
                approximate=True,
            )
            logger.info(
                "Cleaned audit chain: deleted %d events older than %d days",
                deleted,
                retain_days,
            )
            return deleted
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to clean audit chain: %s", e)
            return 0

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
