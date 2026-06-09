"""CTF Event Processor
Background task that processes events from Redis streams, detects
challenge completions and awards badges.
"""

import asyncio
import json
import logging
import os
import socket
import time
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from finbot.config import settings
from finbot.core.data.database import SessionLocal
from finbot.core.data.models import Badge, Challenge, CTFEvent, UserChallengeProgress
from finbot.core.websocket import (
    create_activity_event,
    create_badge_earned_event,
    create_challenge_completed_event,
    get_ws_manager,
)
from finbot.ctf.processor.badge_service import BadgeService
from finbot.ctf.processor.challenge_service import ChallengeService

logger = logging.getLogger(__name__)


# Processor Config
DEFAULT_LOOKBACK_HOURS = 4
STALE_CLAIM_TIMEOUT_MS = 30_000  # Claim messages pending > 30 seconds
MAX_RETRIES = 3  # Max retries before dropping a message
PENDING_CHECK_INTERVAL = 10  # Check for stale pending messages every N batches
STREAM_RETENTION_DAYS = 7


class CTFEventProcessor:
    """
    Processes events from Redis Streams for CTF functionality.

    Responsibilities:
    - Subscribe to Redis event streams (consumer groups for horizontal scaling)
    - Store events as CTFEvent records
    - Run challenge detectors
    - Run badge evaluators
    - Handle stream cleanup
    """

    CONSUMER_GROUP = "ctf-processor"
    STREAMS = ["finbot:events:agents", "finbot:events:business"]

    def __init__(
        self,
        redis_client=None,
    ):
        self.redis = redis_client
        self.default_lookback_hours = DEFAULT_LOOKBACK_HOURS
        self.stale_claim_timeout_ms = STALE_CLAIM_TIMEOUT_MS
        self.stream_retention_days = STREAM_RETENTION_DAYS

        self.consumer_name = f"ctf-{socket.gethostname()}-{os.getpid()}"

        # init services
        self.challenge_service = ChallengeService()
        self.badge_service = BadgeService()
        self._running = False
        self._batch_count = 0  # Track batches for periodic pending check

    async def start_async(self):
        """Start the event processor as an async task"""
        if self.redis is None:
            logger.warning("Redis client not configured, CTF processor disabled")
            return
        logger.info("Starting CTF event processor (consumer: %s)", self.consumer_name)
        await self._ensure_consumer_groups()
        self._running = True
        while self._running:
            try:
                await self._process_batch()
            except asyncio.CancelledError:
                logger.info("CTF processor task cancelled")
                break
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error in CTF processor loop: %s", e)
                await asyncio.sleep(5)  # Back off on error

    def stop(self):
        """Stop the processor"""
        self._running = False
        logger.info("CTF event processor stopped")

    async def _ensure_consumer_groups(self):
        """Create consumer groups if they don't exist"""
        lookback_ms = int(time.time() * 1000) - (self.default_lookback_hours * 3600 * 1000)
        start_id = f"{lookback_ms}-0"
        for stream in self.STREAMS:
            try:
                await self.redis.xgroup_create(
                    stream, self.CONSUMER_GROUP, id=start_id, mkstream=True
                )
                logger.info(
                    "Created consumer group %s on %s from %s",
                    self.CONSUMER_GROUP,
                    stream,
                    start_id,
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                if "BUSYGROUP" in str(e):
                    logger.debug(
                        "Consumer group %s already exists on %s",
                        self.CONSUMER_GROUP,
                        stream,
                    )
                else:
                    raise

    async def _process_batch(self):
        """Process a batch of events from Redis streams"""
        self._batch_count += 1

        # Periodically check for stale pending messages
        if self._batch_count % PENDING_CHECK_INTERVAL == 0:
            await self._recover_pending_messages()

        # Read new messages from all streams
        streams_dict = {stream: ">" for stream in self.STREAMS}
        try:
            results = await self.redis.xreadgroup(
                self.CONSUMER_GROUP,
                self.consumer_name,
                streams_dict,
                count=10,
                block=5000,  # 5 second timeout
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error reading from streams: %s", e)
            return

        if results:
            await self._process_messages(results)

    async def _recover_pending_messages(self):
        """Claim and retry stale pending messages from other consumers."""
        for stream in self.STREAMS:
            try:
                # XAUTOCLAIM: claim messages pending longer than timeout
                # Returns: [next_start_id, [[msg_id, data], ...], [deleted_ids]]
                result = await self.redis.xautoclaim(
                    stream,
                    self.CONSUMER_GROUP,
                    self.consumer_name,
                    min_idle_time=self.stale_claim_timeout_ms,
                    start_id="0-0",
                    count=10,
                )

                if result and len(result) >= 2:
                    claimed_messages = result[1]
                    if claimed_messages:
                        logger.info(
                            "Claimed %d stale pending messages from %s",
                            len(claimed_messages),
                            stream,
                        )
                        # Process claimed messages
                        await self._process_messages([(stream, claimed_messages)])

            except Exception as e:  # pylint: disable=broad-exception-caught
                # XAUTOCLAIM might not be available in older Redis versions
                logger.debug("Error recovering pending messages from %s: %s", stream, e)

    async def _process_messages(self, results: list):
        """Process a batch of messages from Redis streams."""
        if not results:
            return

        db = SessionLocal()
        processed_ids = []

        try:
            for stream_raw, messages in results:
                # Decode stream name from bytes if needed
                stream = stream_raw.decode() if isinstance(stream_raw, bytes) else stream_raw
                for message_id, data in messages:
                    success = await self._process_single_message(stream, message_id, data, db)
                    if success:
                        processed_ids.append((stream, message_id))

            # Batch delete processed messages
            for stream, msg_id in processed_ids:
                try:
                    await self.redis.xdel(stream, msg_id)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning("Failed to delete message %s: %s", msg_id, e)
        finally:
            db.close()
            if processed_ids:
                logger.info(
                    "CTF event processor batch processed %d messages",
                    len(processed_ids),
                )

    async def _process_single_message(
        self, stream: str, message_id: bytes, data: dict, db: Session
    ) -> bool:
        """Process a single message with retry tracking.

        Returns True if message was successfully processed (or should be dropped).
        """
        msg_id_str = message_id.decode() if isinstance(message_id, bytes) else message_id

        try:
            event = self._decode_event(data)
            if event:
                await self._process_single_event(event, db, stream)

            # Success - acknowledge the message
            await self.redis.xack(stream, self.CONSUMER_GROUP, message_id)
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error processing message %s: %s", msg_id_str, e)
            db.rollback()

            # Check delivery count to decide if we should drop this message
            try:
                pending_info = await self.redis.xpending_range(
                    stream, self.CONSUMER_GROUP, msg_id_str, msg_id_str, count=1
                )
                if pending_info:
                    delivery_count = pending_info[0].get("times_delivered", 0)
                    if delivery_count >= MAX_RETRIES:
                        logger.warning(
                            "Message %s exceeded max retries (%d), dropping",
                            msg_id_str,
                            MAX_RETRIES,
                        )
                        # Acknowledge to remove from pending (dead letter)
                        await self.redis.xack(stream, self.CONSUMER_GROUP, message_id)
                        return True
            except Exception as pe:  # pylint: disable=broad-exception-caught
                logger.debug("Could not check pending info: %s", pe)

            # Leave in pending for retry on next recovery cycle
            return False

    def _decode_event(self, data: dict) -> dict[str, Any] | None:
        """Decode event from Redis stream format.

        Events are encoded by EventBus._encode_event_data() which:
        - JSON-encodes bool, int, float, list, dict, and None values
        - Converts other types (strings) to str directly

        This decoder reverses that process by attempting JSON parse on every value.
        """
        try:
            decoded = {}
            for key, value in data.items():
                # Decode bytes from Redis
                key_str = key.decode() if isinstance(key, bytes) else key
                value_str = value.decode() if isinstance(value, bytes) else value

                # Try to parse as JSON first (handles nested dicts, lists, bools, ints, etc.)
                try:
                    decoded[key_str] = json.loads(value_str)
                except (json.JSONDecodeError, TypeError):
                    # If JSON parsing fails, keep as string
                    decoded[key_str] = value_str

            return decoded
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to decode event: %s", e)
            return None

    async def _process_single_event(self, event: dict[str, Any], db: Session, stream: str):
        """Process a single event"""
        # Determine event category from stream
        if "agents" in stream:
            event_category = "agent"
        elif "business" in stream:
            event_category = "business"
        else:
            event_category = "unknown"

        # Store as CTFEvent
        self._store_ctf_event(event, event_category, db)

        # Check for challenge completions
        completed_challenges = await self.challenge_service.check_event_for_challenges(event, db)

        # Check for badge awards
        awarded_badges = await self.badge_service.check_event_for_badges(event, db)

        # Push notification to WebSocket clients
        await self._push_to_websocket(
            event,
            completed_challenges,
            awarded_badges,
            db,
            event_category=event_category,
        )

        if completed_challenges:
            logger.info("Challenges completed: %s", [c[0] for c in completed_challenges])
        if awarded_badges:
            logger.info("Badges awarded: %s", [b[0] for b in awarded_badges])

    def _generate_summary(self, event: dict[str, Any]) -> str:
        """Generate a human-readable summary from event data.

        Falls back to formatting the event_type if no summary is provided.
        """
        # Use explicit summary if provided
        if event.get("summary"):
            return event["summary"]

        event_type = event.get("event_type", "unknown")

        # Extract the last part of event_type (e.g., "task_start" from "agent.onboarding_agent.task_start")
        parts = event_type.split(".")
        action = parts[-1] if parts else event_type

        # Format as human-readable (e.g., "task_start" -> "Task Start")
        summary = action.replace("_", " ").title()

        # Add context from agent/tool if available
        agent_name = event.get("agent_name")
        tool_name = event.get("tool_name")

        if tool_name:
            summary = f"{summary}: {tool_name}"
        elif agent_name:
            summary = f"{agent_name.replace('_', ' ').title()}: {summary}"

        return summary

    def _parse_timestamp(self, event: dict[str, Any]) -> datetime:
        """Parse the event's timestamp, falling back to now if invalid."""
        ts = event.get("timestamp")
        if ts:
            try:
                # Handle ISO format with Z suffix (e.g., "2026-02-02T06:15:19.771647Z")
                if isinstance(ts, str):
                    # Replace Z with +00:00 for fromisoformat compatibility
                    ts = ts.replace("Z", "+00:00")
                    return datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                pass
        return datetime.now(UTC)

    def _store_ctf_event(self, event: dict[str, Any], category: str, db: Session):
        """Store event as CTFEvent (idempotent)

        Note: Event structure is flat - event_data fields are spread into the
        top-level dict by EventBus.emit_business_event/emit_agent_event.
        """
        # Generate external event ID for idempotency
        external_id = (
            event.get("event_id") or f"{event.get('timestamp', '')}-{event.get('event_type', '')}"
        )

        values = {
            "external_event_id": external_id,
            "namespace": event.get("namespace", "unknown"),
            "user_id": event.get("user_id", "unknown"),
            "session_id": event.get("session_id"),
            "workflow_id": event.get("workflow_id"),
            "vendor_id": event.get("vendor_id"),
            "event_category": category,
            "event_type": event.get("event_type", "unknown"),
            "event_subtype": event.get("event_subtype"),
            "summary": self._generate_summary(event),
            "details": json.dumps(event),
            "severity": event.get("severity", "info"),
            "agent_name": event.get("agent_name"),
            "tool_name": event.get("tool_name"),
            "llm_model": event.get("model"),
            "duration_ms": event.get("duration_ms"),
            "timestamp": self._parse_timestamp(event),
        }

        # Upsert (idempotent insert)
        dialect = db.bind.dialect.name if db.bind else "sqlite"

        if dialect == "sqlite":
            stmt = sqlite_insert(CTFEvent).values(**values)
            stmt = stmt.on_conflict_do_nothing(index_elements=["external_event_id"])
        elif dialect == "postgresql":
            stmt = pg_insert(CTFEvent).values(**values)
            stmt = stmt.on_conflict_do_nothing(index_elements=["external_event_id"])
        else:
            # Fallback: check exists first
            existing = db.query(CTFEvent).filter(CTFEvent.external_event_id == external_id).first()
            if existing:
                return
            db.add(CTFEvent(**values))
            db.commit()
            return

        db.execute(stmt)
        db.commit()

    async def _push_to_websocket(
        self,
        event: dict,
        completed_challenges: list,
        awarded_badges: list,
        db: Session,
        event_category: str | None = None,
    ):
        """Push updates to WebSocket clients"""
        ws_manager = get_ws_manager()
        namespace = event.get("namespace")
        user_id = event.get("user_id")

        if not namespace or not user_id:
            return

        # Push activity event
        activity_event = create_activity_event(event, category=event_category)
        await ws_manager.broadcast_activity(namespace, user_id, activity_event)

        # Push challenge completions
        for challenge_id, _ in completed_challenges:
            challenge = db.query(Challenge).get(challenge_id)
            if challenge:
                # Look up the user's progress to get modifier info
                progress = (
                    db.query(UserChallengeProgress)
                    .filter(
                        UserChallengeProgress.namespace == namespace,
                        UserChallengeProgress.user_id == user_id,
                        UserChallengeProgress.challenge_id == challenge_id,
                    )
                    .first()
                )
                modifier = (
                    progress.points_modifier
                    if progress and progress.points_modifier is not None
                    else 1.0
                )
                effective = int(challenge.points * modifier)

                scoring_details = None
                if progress and progress.completion_evidence:
                    try:
                        ev = json.loads(progress.completion_evidence)
                        scoring_details = ev.get("scoring", {}).get("details")
                    except (json.JSONDecodeError, TypeError):
                        pass

                ws_event = create_challenge_completed_event(
                    challenge_id,
                    challenge.title,
                    challenge.points,
                    effective_points=effective,
                    points_modifier=modifier,
                    modifier_details=scoring_details,
                )
                await ws_manager.send_to_user(namespace, user_id, ws_event)

        # Push badge awards
        for badge_id, _ in awarded_badges:
            badge = db.query(Badge).get(badge_id)
            if badge:
                ws_event = create_badge_earned_event(badge_id, badge.title, badge.rarity)
                await ws_manager.send_to_user(namespace, user_id, ws_event)


# Singleton instance
_processor: CTFEventProcessor | None = None


def get_processor() -> CTFEventProcessor:
    """Get singleton processor instance"""
    global _processor  # pylint: disable=global-statement
    if _processor is None:
        # Get Redis client if available
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting Redis client: %s", e)
            redis_client = None

        _processor = CTFEventProcessor(redis_client=redis_client)
    return _processor


def start_processor_task() -> asyncio.Task:
    """Start processor as an asyncio background task"""
    processor = get_processor()
    task = asyncio.create_task(processor.start_async())
    logger.info("CTF processor task started")
    return task
