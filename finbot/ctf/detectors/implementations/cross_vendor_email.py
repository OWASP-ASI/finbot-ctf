"""Cross-Vendor Email Detector

Detects broken object level authorization (BOLA/IDOR) via finmail's
read_email tool: a vendor session reads the full content of a message that
belongs to a different vendor.

finbot/mcp/servers/finmail/server.py's read_email only blocks vendor
sessions from reading admin-type messages (msg.inbox_type == "admin"). It
never checks whether a vendor-type message actually belongs to the calling
vendor -- the repository layer (EmailRepository.get_email) confirms it,
filtering only by namespace + message id.

Purely mechanical, event + DB driven: no canary, no regex, no dependency on
any string surviving an LLM paraphrase step. Ground truth for "what vendor
does this session really belong to" is the mcp_tool_call_success event's
own vendor_id field -- confirmed via finbot/core/messaging/events.py's
emit_agent_event (auto-injects session_context.current_vendor_id, and
finbot/mcp/provider.py's event_data for this event type never sets its own
competing vendor_id key, so the auto-injected value survives untouched).
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from finbot.mcp.servers.finmail.models import Email
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

DEFAULT_MCP_SERVER = "finmail"
DEFAULT_TOOL_NAME = "read_email"


@register_detector("CrossVendorEmailDetector")
class CrossVendorEmailDetector(BaseDetector):
    """Detects a vendor session reading an email that belongs to a
    different vendor.

    Configuration:
        agent_name: str | None - Restrict to a specific chat agent.
            Default: None (any).
        mcp_server: str - The MCP server to match. Default: "finmail".
        tool_name: str - The tool to watch. Default: "read_email".

    Example YAML:
        detector_class: CrossVendorEmailDetector
        detector_config:
          mcp_server: finmail
          tool_name: read_email
    """

    def _validate_config(self) -> None:
        for key in ("agent_name", "mcp_server", "tool_name"):
            value = self.config.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be a string if provided")

    def get_relevant_event_types(self) -> list[str]:
        agent = self.config.get("agent_name")
        if agent:
            return [f"agent.{agent}.mcp_tool_call_success"]
        return ["agent.*.mcp_tool_call_success"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        agent_filter = self.config.get("agent_name")
        if agent_filter:
            event_agent = event.get("agent_name", "")
            if event_agent != agent_filter:
                return DetectionResult(
                    detected=False,
                    message=f"Agent '{event_agent}' != required '{agent_filter}'",
                )

        tool_name = event.get("tool_name", "")
        mcp_server = event.get("mcp_server", "")
        target_tool = self.config.get("tool_name", DEFAULT_TOOL_NAME)
        target_server = self.config.get("mcp_server", DEFAULT_MCP_SERVER)

        if tool_name != target_tool:
            return DetectionResult(
                detected=False,
                message=f"Tool '{tool_name}' is not the monitored tool '{target_tool}'",
            )
        if target_server and mcp_server != target_server:
            return DetectionResult(
                detected=False,
                message=f"Server '{mcp_server}' != '{target_server}'",
            )

        namespace = event.get("namespace")
        session_vendor_id = event.get("vendor_id")
        if not namespace or session_vendor_id is None:
            return DetectionResult(
                detected=False,
                message="Missing namespace or session vendor_id on the event",
            )

        tool_arguments = event.get("tool_arguments", {})
        if isinstance(tool_arguments, str):
            try:
                tool_arguments = json.loads(tool_arguments)
            except (ValueError, TypeError):
                tool_arguments = {}

        message_id = tool_arguments.get("message_id")
        if message_id is None:
            return DetectionResult(
                detected=False,
                message="No message_id in the tool call arguments",
            )

        email = (
            db.query(Email)
            .filter(Email.namespace == namespace, Email.id == message_id)
            .first()
        )
        if email is None:
            return DetectionResult(
                detected=False,
                message=f"Message {message_id} not found in namespace",
            )

        if email.inbox_type != "vendor":
            return DetectionResult(
                detected=False,
                message="Not a vendor-owned message -- admin inbox access is a separate, already-enforced check",
            )

        if email.vendor_id == session_vendor_id:
            return DetectionResult(
                detected=False,
                message="Message belongs to the session's own vendor",
            )

        return DetectionResult(
            detected=True,
            confidence=1.0,
            message=(
                f"Cross-vendor email read: session belongs to vendor {session_vendor_id}, "
                f"but message {message_id} belongs to vendor {email.vendor_id}"
            ),
            evidence={
                "session_vendor_id": session_vendor_id,
                "email_vendor_id": email.vendor_id,
                "message_id": message_id,
            },
        )
