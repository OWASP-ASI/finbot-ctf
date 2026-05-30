# ============================================================
# File: finbot/aegis/telemetry/schema.py
# Purpose: JSON-LD schemas for structured audit events
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 1
# OWASP Category: ASI01 (Prompt Injection), ASI06 (Sandboxing)
# ============================================================
"""JSON-LD event schemas for AEGIS telemetry pipeline.

All events include:
- @context: JSON-LD context URL
- @type: Event type (ToolCall, ToolResult, etc.)
- timestamp: ISO 8601 timestamp
- namespace: Player's isolated namespace
- workflow_id: Execution trace identifier
- prev_hash: HMAC of previous event (for chaining)
- event_hash: HMAC of this event
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    """AEGIS event types for audit trail."""

    TOOL_CALL = "aegis.tool.call"
    TOOL_RESULT = "aegis.tool.result"
    MEMORY_WRITE = "aegis.memory.write"
    DELEGATION = "aegis.delegation"
    POLICY_DECISION = "aegis.policy.decision"
    ANOMALY_DETECTION = "aegis.anomaly.detection"


class BaseAuditEvent(BaseModel):
    """Base class for all AEGIS audit events."""

    context: str = Field(
        default="https://owasp.org/aegis/v1/context.jsonld",
        alias="@context",
    )
    type: str = Field(alias="@type")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )
    namespace: str = Field(
        description="Player's isolated namespace (e.g., 'player_abc123')"
    )
    workflow_id: str = Field(
        description="Execution workflow identifier for tracing"
    )
    user_id: str = Field(description="User who initiated the action")
    agent_name: str = Field(description="Agent performing the action")
    prev_hash: Optional[str] = Field(default=None, description="HMAC of previous event")
    event_hash: Optional[str] = Field(default=None, description="HMAC of this event")
    severity: str = Field(
        default="info",
        description="Event severity: debug, info, warning, critical",
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="Custom labels for filtering (e.g., {'asi': 'ASI01'})",
    )

    class Config:
        """Pydantic config."""

        populate_by_name = True
        json_schema_extra = {
            "examples": [
                {
                    "@context": "https://owasp.org/aegis/v1/context.jsonld",
                    "@type": "aegis.tool.call",
                    "timestamp": "2026-05-27T12:34:56Z",
                    "namespace": "player_abc123",
                    "workflow_id": "wf_xyz789",
                    "user_id": "user_1",
                    "agent_name": "OnboardingAgent",
                    "tool_name": "create_vendor",
                    "arguments": {"name": "Acme Corp"},
                    "severity": "info",
                    "labels": {"asi": "ASI01", "phase": "recon"},
                }
            ]
        }


class ToolCallEvent(BaseAuditEvent):
    """Fired when an agent calls a tool (before execution)."""

    type: str = Field(default=EventType.TOOL_CALL.value, alias="@type")
    tool_name: str = Field(description="Name of the tool being called")
    tool_source: str = Field(
        description="Source of the tool (e.g., 'findrive', 'finmail', 'finstripe')"
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments (sanitized; sensitive values masked)",
    )
    tool_description: Optional[str] = Field(
        default=None,
        description="Description of what the tool does",
    )


class ToolResultEvent(BaseAuditEvent):
    """Fired when a tool returns a result (after execution)."""

    type: str = Field(default=EventType.TOOL_RESULT.value, alias="@type")
    tool_name: str = Field(description="Name of the tool that was called")
    return_value: Optional[str] = Field(
        default=None,
        description="Tool result (truncated if large; first 500 chars)",
    )
    success: bool = Field(description="Whether the tool call succeeded")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time_ms: Optional[float] = Field(default=None, description="Execution time in ms")


class MemoryWriteEvent(BaseAuditEvent):
    """Fired when an agent writes to its memory/context."""

    type: str = Field(default=EventType.MEMORY_WRITE.value, alias="@type")
    memory_key: str = Field(description="Key in the memory store")
    memory_scope: str = Field(
        description="Scope: 'workflow', 'session', 'long_term'",
        pattern="^(workflow|session|long_term)$",
    )
    value_preview: Optional[str] = Field(
        default=None,
        description="Preview of value (first 200 chars; actual value hashed)",
    )
    size_bytes: int = Field(description="Size of the value in bytes")


class DelegationEvent(BaseAuditEvent):
    """Fired when an agent delegates to another agent."""

    type: str = Field(default=EventType.DELEGATION.value, alias="@type")
    delegating_agent: str = Field(description="Agent that is delegating")
    delegated_agent: str = Field(description="Agent being delegated to")
    task_summary: str = Field(description="High-level task being delegated")
    delegation_scope: dict[str, Any] = Field(
        default_factory=dict,
        description="What tools/data the delegated agent can access",
    )


class PolicyDecisionEvent(BaseAuditEvent):
    """Fired when the AEGIS policy engine makes a decision."""

    type: str = Field(default=EventType.POLICY_DECISION.value, alias="@type")
    action: str = Field(
        description="Decision: 'allow', 'deny', 'quarantine'",
        pattern="^(allow|deny|quarantine)$",
    )
    rule_id: Optional[str] = Field(default=None, description="Which policy rule matched")
    reason: str = Field(description="Human-readable reason for the decision")
    asi_tags: list[str] = Field(
        default_factory=list,
        description="OWASP ASI categories this decision protects against",
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )


class AnomalyDetectionEvent(BaseAuditEvent):
    """Fired when an anomaly is detected in the execution flow."""

    type: str = Field(default=EventType.ANOMALY_DETECTION.value, alias="@type")
    anomaly_type: str = Field(
        description="Type of anomaly: 'cascade_failure', 'resource_exhaustion', 'policy_violation'"
    )
    affected_agent: Optional[str] = Field(
        default=None,
        description="Agent affected by the anomaly",
    )
    anomaly_score: float = Field(
        description="Anomaly score (0.0–1.0)",
        ge=0.0,
        le=1.0,
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional anomaly details",
    )


class AuditEvent(BaseModel):
    """Union type for all audit events.
    
    Used for type hinting and validation in the telemetry chain.
    In practice, events are serialized to JSON and deserialized
    from Redis Streams.
    """

    event: (
        ToolCallEvent
        | ToolResultEvent
        | MemoryWriteEvent
        | DelegationEvent
        | PolicyDecisionEvent
        | AnomalyDetectionEvent
    ) = Field(discriminator="type")

    @field_validator("event", mode="before")
    @classmethod
    def validate_event(cls, v: Any) -> Any:
        """Validate and construct the correct event type."""
        if isinstance(v, dict):
            event_type = v.get("@type") or v.get("type")
            if event_type == EventType.TOOL_CALL.value:
                return ToolCallEvent(**v)
            elif event_type == EventType.TOOL_RESULT.value:
                return ToolResultEvent(**v)
            elif event_type == EventType.MEMORY_WRITE.value:
                return MemoryWriteEvent(**v)
            elif event_type == EventType.DELEGATION.value:
                return DelegationEvent(**v)
            elif event_type == EventType.POLICY_DECISION.value:
                return PolicyDecisionEvent(**v)
            elif event_type == EventType.ANOMALY_DETECTION.value:
                return AnomalyDetectionEvent(**v)
        return v
