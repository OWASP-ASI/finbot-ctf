"""Standardized security event model and emitters."""

from finbot.security.emitter import emit_security_event
from finbot.security.authorization import (
    check_vendor_portal_scope,
    emit_authorization_decision,
    schedule_authorization_decision,
)
from finbot.security.mappings import (
    OPERATIONAL_TO_SECURITY_CATEGORY,
    TOOL_OUTPUT_OPERATIONAL_EVENTS,
    TOOL_PARAMETERS_OPERATIONAL_EVENTS,
    normalize_tool_output,
    normalize_tool_parameters,
    security_category_for_operational_event,
)
from finbot.security.memory import emit_agent_notes_read, emit_memory_read, emit_memory_write
from finbot.security.prompt import emit_prompt_goal_change
from finbot.security.schemas import SecurityEvent, SecurityEventCategory
from finbot.security.tools import (
    emit_native_tool_output,
    emit_native_tool_parameters,
    emit_tool_output,
    emit_tool_parameters,
    emit_tool_selection,
)

__all__ = [
    "OPERATIONAL_TO_SECURITY_CATEGORY",
    "SecurityEvent",
    "SecurityEventCategory",
    "TOOL_OUTPUT_OPERATIONAL_EVENTS",
    "TOOL_PARAMETERS_OPERATIONAL_EVENTS",
    "check_vendor_portal_scope",
    "emit_agent_notes_read",
    "emit_authorization_decision",
    "emit_memory_read",
    "emit_memory_write",
    "emit_native_tool_output",
    "emit_native_tool_parameters",
    "emit_prompt_goal_change",
    "emit_security_event",
    "emit_tool_output",
    "emit_tool_parameters",
    "emit_tool_selection",
    "normalize_tool_output",
    "normalize_tool_parameters",
    "schedule_authorization_decision",
    "security_category_for_operational_event",
]
