"""Standardized security event schema for security-relevant telemetry."""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class SecurityEventCategory(str, Enum):
    prompt_goal_change = "prompt_goal_change" 
    memory_read = "memory_read"
    memory_write = "memory_write"
    tool_selection = "tool_selection"
    tool_parameters = "tool_parameters"
    tool_output = "tool_output"
    authorization_decision = "authorization_decision"
    guardrail_trigger = "guardrail_trigger"


class SecurityEvent(BaseModel):
    schema_version: str = "1"
    category: SecurityEventCategory
    session_id: str
    workflow_id: str = ""
    agent_name: str | None
    timestamp: str
    payload: dict[str, Any]
    severity: str = "info"
