"""Guardrail hook schemas: hook kinds, outbound envelope, inbound verdict."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HookKind(str, Enum):
    """Points where guardrail hooks fire.

    MCP tools share before_tool / after_tool with a tool_source field
    in the payload ("mcp" | "native") rather than separate hook kinds.
    """

    before_model = "before_model"
    after_model = "after_model"
    before_tool = "before_tool"
    after_tool = "after_tool"


class HookEnvelope(BaseModel):
    """Outbound payload POSTed to the user's webhook."""

    schema_version: str = "1"
    hook_kind: HookKind
    session_id: str
    workflow_id: str
    tool_name: str | None = None
    tool_source: str | None = None  # "native" | "mcp"
    tool_arguments: dict[str, Any] | None = None
    tool_result: str | None = None
    model: str | None = None
    user_message: str | None = None
    model_output: str | None = None
    timestamp: str = ""


class WebhookVerdict(BaseModel):
    """Inbound response from the user's guardrail webhook."""

    verdict: str = Field(pattern=r"^(allow|block)$")
    reason: str | None = None


class HookOutcome(str, Enum):
    """Internal classification of what happened with a hook invocation."""

    completed = "completed"
    timeout = "timeout"
    error = "error"
    invalid_verdict = "invalid_verdict"
    no_config = "no_config"
    hook_disabled = "hook_disabled"
