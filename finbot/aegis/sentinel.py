# ============================================================
# File: finbot/aegis/sentinel.py
# Purpose: Hash-chained HMAC audit trail on Redis via EventBus
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 2
# OWASP Category: ASI06 Memory Poisoning, ASI08 Cascading Failures
# ============================================================
"""SentinelStream: hash-chained forensic audit events on Redis."""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

from finbot.aegis.schemas import AuditEvent
from finbot.config import settings
from finbot.core.auth.session import SessionContext
from finbot.core.messaging import event_bus

logger = logging.getLogger(__name__)


class SentinelStream:
    """Records tamper-evident audit events with per-namespace hash chains."""

    def __init__(self) -> None:
        self._chain_key = "aegis:audit:chain_head"
        signing_key = settings.SESSION_SIGNING_KEY or settings.SECRET_KEY
        self._signing_key = signing_key.encode()

    async def record(
        self,
        *,
        event_type: str,
        namespace: str,
        workflow_id: str,
        agent_name: str,
        payload: dict[str, Any],
        session_context: SessionContext,
    ) -> AuditEvent:
        prev_hash = await self._get_chain_head(namespace)
        timestamp = datetime.now(UTC).isoformat()
        body = {
            "event_type": event_type,
            "namespace": namespace,
            "workflow_id": workflow_id,
            "agent_name": agent_name,
            "payload": payload,
            "timestamp": timestamp,
            "prev_hash": prev_hash,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        event_hash = hmac.new(
            self._signing_key,
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        audit = AuditEvent(**body, event_hash=event_hash)
        await self._set_chain_head(namespace, event_hash)
        await event_bus.emit_agent_event(
            agent_name="aegis",
            event_type=f"audit.{event_type}",
            event_subtype="security",
            event_data={**body, "event_hash": event_hash},
            session_context=session_context,
            workflow_id=workflow_id,
            summary=f"AEGIS audit: {event_type}",
        )
        return audit

    async def _get_chain_head(self, namespace: str) -> str | None:
        key = f"{self._chain_key}:{namespace}"
        try:
            val = await event_bus.redis.get(key)
            if val is None:
                return None
            return val.decode() if isinstance(val, bytes) else str(val)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Could not read AEGIS chain head for %s", namespace, exc_info=True)
            return None

    async def _set_chain_head(self, namespace: str, digest: str) -> None:
        key = f"{self._chain_key}:{namespace}"
        try:
            await event_bus.redis.set(key, digest, ex=settings.AEGIS_AUDIT_CHAIN_TTL)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Could not write AEGIS chain head for %s", namespace, exc_info=True)
