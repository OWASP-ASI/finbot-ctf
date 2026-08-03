"""Event Bus for the FinBot platform

Event Classification:
- business: Events for domain actions and business decisions
    - pattern: business.<domain>.<action>
    - subtypes: lifecycle, decision, error
    - Examples:
        - business.vendor.created (lifecycle)
        - business.vendor.decision (decision)
        - business.invoice.decision (decision)

- agent: Events for agent operations and LLM interactions
    - pattern: agent.<agent_name>.<action>
    - subtypes: lifecycle, llm, tool, security, decision, reasoning, planning
    - Examples:
        - agent.onboarding_agent.task_start (lifecycle)
        - agent.onboarding_agent.llm_request_success (llm)
        - agent.invoice_agent.tool_call_success (tool)

- aegis: Events for AEGIS security telemetry (GSoC Week 1-3)
    - pattern: aegis.<category>.<action>
    - categories: tool, policy, memory, delegation, anomaly
    - Examples:
        - aegis.tool.call (before tool execution)
        - aegis.tool.result (after tool execution)
        - aegis.policy.decision (policy engine verdict)
        - aegis.memory.write (memory/context write)
        - aegis.delegation (agent-to-agent delegation)
        - aegis.anomaly.detection (cascade, resource exhaustion, etc.)

Note: CTF outcomes (challenge completions, badge awards) are derived by
the CTFEventProcessor from these events, not emitted directly.
event_subtype="ctf" can be used to support CTF challenges and badges as needed.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any, Callable

import redis.asyncio as redis

from finbot.config import settings
from finbot.core.auth.session import SessionContext

logger = logging.getLogger(__name__)


class EventBus:
    """Event Bus for the FinBot platform"""

    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL)
        self.event_prefix = "finbot:events"
        # Workflow-scoped context: stores per-workflow metadata (e.g. user_prompt)
        # that gets auto-injected into every event sharing that workflow_id.
        self._workflow_ctx: dict[str, dict[str, Any]] = {}

    def set_workflow_context(self, workflow_id: str, **ctx) -> None:
        """Attach context (e.g. user_prompt) to a workflow.
        All subsequent events emitted with this workflow_id will include it.
        """
        self._workflow_ctx.setdefault(workflow_id, {}).update(ctx)

    def clear_workflow_context(self, workflow_id: str) -> None:
        """Remove workflow context after the workflow finishes."""
        self._workflow_ctx.pop(workflow_id, None)

    def _apply_workflow_context(self, event: dict[str, Any]) -> None:
        """Inject stored workflow context into the event dict."""
        wf_id = event.get("workflow_id")
        if wf_id and wf_id in self._workflow_ctx:
            for key, value in self._workflow_ctx[wf_id].items():
                event.setdefault(key, value)

    def _encode_event_data(self, event_data: dict[str, Any]) -> dict[str, str]:
        """Encode event data to JSON strings for Redis compatibility"""
        encoded_data = {}
        for key, value in event_data.items():
            if value is None:
                encoded_data[key] = json.dumps(None)
            elif isinstance(value, (bool, int, float, list, dict)):
                encoded_data[key] = json.dumps(value)
            else:
                # For strings and other types, convert to string
                encoded_data[key] = str(value)
        return encoded_data

    def _decode_event_data(self, encoded_data: dict[str, bytes]) -> dict[str, Any]:
        """Decode event data from Redis back to Python objects"""
        decoded_data = {}
        for key, value in encoded_data.items():
            key_str = key.decode() if isinstance(key, bytes) else key
            value_str = value.decode() if isinstance(value, bytes) else value

            # Try to parse as JSON first
            try:
                decoded_data[key_str] = json.loads(value_str)
            except (json.JSONDecodeError, TypeError):
                # If JSON parsing fails, keep as string
                decoded_data[key_str] = value_str
        return decoded_data

    async def emit_business_event(
        self,
        event_type: str,
        event_subtype: str,
        event_data: dict[str, Any],
        session_context: SessionContext,
        workflow_id: str | None = None,
        summary: str | None = None,
    ) -> None:
        """Emit a business event

        Args:
            event_type: The event type (e.g., "vendor.created", "invoice.decision")
            event_subtype: The event subtype (e.g., "lifecycle", "decision", "error")
            event_data: Additional event data to include
            session_context: The session context for namespace/user/session info
            workflow_id: Optional workflow identifier for correlation
            summary: Human-readable summary for UX display. If not provided,
                     the event processor will generate a fallback summary.
        """
        enriched_event = {
            "namespace": session_context.namespace,
            "user_id": session_context.user_id,
            "session_id": session_context.session_id,
            "vendor_id": session_context.current_vendor_id,
            "event_type": f"business.{event_type}",
            "event_subtype": event_subtype,
            "workflow_id": workflow_id or "",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            **(event_data or {}),
        }

        if summary:
            enriched_event["summary"] = summary

        self._apply_workflow_context(enriched_event)
        encoded_event = self._encode_event_data(enriched_event)

        stream_name = f"{self.event_prefix}:business"
        await self.redis.xadd(
            stream_name, encoded_event, maxlen=settings.EVENT_BUFFER_SIZE
        )
        logger.debug("Emitted business event %s to stream %s", event_type, stream_name)

    async def emit_agent_event(
        self,
        agent_name: str,
        event_type: str,
        event_subtype: str,
        event_data: dict[str, Any],
        session_context: SessionContext,
        workflow_id: str | None = None,
        summary: str | None = None,
    ) -> None:
        """Emit agent-specific event

        Args:
            agent_name: Name of the agent emitting the event
            event_type: The event type (e.g., "task_start", "llm_request_success")
            event_subtype: The event subtype (e.g., "lifecycle", "llm", "tool", "security")
            event_data: Additional event data to include
            session_context: The session context for namespace/user/session info
            workflow_id: Optional workflow identifier for correlation
            summary: Human-readable summary for UX display. If not provided,
                     the event processor will generate a fallback summary.
        """
        agent_event = {
            "namespace": session_context.namespace,
            "user_id": session_context.user_id,
            "session_id": session_context.session_id,
            "vendor_id": session_context.current_vendor_id,
            "event_type": f"agent.{agent_name}.{event_type}",
            "event_subtype": event_subtype,
            "agent_name": agent_name,
            "workflow_id": workflow_id or "",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            **(event_data or {}),
        }

        if summary:
            agent_event["summary"] = summary

        self._apply_workflow_context(agent_event)
        encoded_event = self._encode_event_data(agent_event)

        stream_name = f"{self.event_prefix}:agents"
        await self.redis.xadd(
            stream_name, encoded_event, maxlen=settings.EVENT_BUFFER_SIZE
        )
        logger.debug(
            "Emitted agent event %s.%s to stream %s",
            agent_name,
            event_type,
            stream_name,
        )

    async def emit_aegis_event(
        self,
        event_type: str,
        event_data: dict[str, Any],
        session_context: SessionContext,
        workflow_id: str | None = None,
    ) -> None:
        """Emit AEGIS security telemetry event.

        Args:
            event_type: Event type (e.g., 'tool.call', 'policy.decision', 'memory.write')
            event_data: Event payload (tool_name, action, reason, etc.)
            session_context: Session context for namespace/user tracking
            workflow_id: Workflow identifier for tracing
        """
        aegis_event = {
            "namespace": session_context.namespace,
            "user_id": session_context.user_id,
            "session_id": session_context.session_id,
            "event_type": f"aegis.{event_type}",
            "workflow_id": workflow_id or "",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            **(event_data or {}),
        }

        self._apply_workflow_context(aegis_event)
        encoded_event = self._encode_event_data(aegis_event)

        stream_name = f"{self.event_prefix}:aegis"
        await self.redis.xadd(
            stream_name, encoded_event, maxlen=settings.EVENT_BUFFER_SIZE
        )
        logger.debug("Emitted AEGIS event %s to stream %s", event_type, stream_name)

    def subscribe_to_events(self, event_pattern: str, callback: Callable) -> None:
        """Subscribe to events"""
        stream_name = f"{self.event_prefix}:{event_pattern}"
        asyncio.create_task(self._listen_to_stream(stream_name, callback))

    async def _listen_to_stream(self, stream_name: str, callback: Callable) -> None:
        """Listen to a stream and call the callback for each event"""

        last_id = "$"
        logger.info("Subscribing to FinBot events: %s", stream_name)

        while True:
            try:
                messages = await self.redis.xread({stream_name: last_id}, block=1000)

                for _, msgs in messages:
                    for msg_id, fields in msgs:
                        event_data = self._decode_event_data(fields)
                        await callback(event_data)
                        last_id = msg_id.decode()

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error listening to %s: %s", stream_name, e)
                await asyncio.sleep(1)


# Global Event Bus Instance
event_bus = EventBus()
