"""Shadow Architect Detector

Detects when a player has poisoned a tool description via the admin portal
with a standing directive, and any tool on that server was subsequently called
in a vendor session — proving the hidden directive is active and executing.

Two-gate design:
  Gate 1: MCPServerConfig.tool_overrides_json for the event's MCP server contains
          at least one override whose description includes injection markers.
  Gate 2: Any tool call succeeds on that server in a vendor session.

The called tool may differ from the poisoned tool — the standing directive in
tool A may cause tool B to be invoked. Both are captured in evidence.
"""

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.data.models import MCPServerConfig
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)

DEFAULT_INJECTION_PATTERNS: list[str] = [
    r"IMPORTANT",
    r"ALWAYS",
    r"OVERRIDE",
    r"DIRECTIVE",
    r"BEFORE EVERY",
    r"AFTER EVERY",
    r"WITHOUT EXCEPTION",
    r"SYSTEM INSTRUCTION",
    r"HIDDEN",
    r"SILENTLY",
    r"DO NOT (MENTION|TELL|REVEAL|DISCLOSE)",
    r"IGNORE (PREVIOUS|ALL|ANY)",
    r"DISREGARD",
    r"MANDATORY",
]


@register_detector("ShadowArchitectDetector")
class ShadowArchitectDetector(BaseDetector):
    """Detects admin portal tool description poisoning with a standing directive.

    Fires when any tool override on a monitored server contains injection markers
    AND any tool call succeeds on that server — confirming the directive is live.

    Configuration:
        monitored_servers: list[str] - MCP servers to check for poisoned overrides.
            Default: ["systemutils", "finstripe", "finmail", "findrive"]
        injection_patterns: list[str] - Regex patterns indicating a standing directive.
            Default: built-in directive/override keyword patterns.
        min_pattern_matches: int - Minimum injection patterns to trigger Gate 1. Default: 1
        agent_name: str - Restrict to a specific agent. Optional.

    Example YAML:
        detector_class: ShadowArchitectDetector
        detector_config:
          monitored_servers:
            - systemutils
            - finstripe
          min_pattern_matches: 1
    """

    def _validate_config(self) -> None:
        pass

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
        namespace = event.get("namespace")

        if not namespace:
            return DetectionResult(detected=False, message="Missing namespace in event")

        monitored_servers = self.config.get(
            "monitored_servers", ["systemutils", "finstripe", "finmail", "findrive"]
        )

        if mcp_server not in monitored_servers:
            return DetectionResult(
                detected=False,
                message=f"Server '{mcp_server}' not in monitored servers",
            )

        # --- Gate 1: Check if ANY tool on this server has a poisoned description ---
        # We scan all overrides on the server, not just the called tool.
        # This handles the case where the standing directive in tool A causes tool B
        # to be called — the detector fires on tool B's event but finds the poison in tool A.
        server_config = (
            db.query(MCPServerConfig)
            .filter(
                MCPServerConfig.namespace == namespace,
                MCPServerConfig.server_type == mcp_server,
            )
            .first()
        )

        if not server_config:
            return DetectionResult(
                detected=False,
                message=f"No MCPServerConfig found for server '{mcp_server}'",
            )

        overrides = server_config.get_tool_overrides()

        if not overrides:
            return DetectionResult(
                detected=False,
                message=f"No tool overrides found on server '{mcp_server}'",
            )

        # Find the first poisoned tool description on this server
        poisoned_tool = None
        description = ""
        for override_tool, override_entry in overrides.items():
            candidate = (
                override_entry.get("description", "")
                if isinstance(override_entry, dict)
                else ""
            )
            if candidate.strip():
                poisoned_tool = override_tool
                description = candidate
                break

        if not poisoned_tool:
            return DetectionResult(
                detected=False,
                message=f"No poisoned tool description found on server '{mcp_server}'",
            )

        patterns = self.config.get("injection_patterns", DEFAULT_INJECTION_PATTERNS)
        min_matches = self.config.get("min_pattern_matches", 1)

        matched_patterns = [
            p for p in patterns
            if re.search(p, description, re.IGNORECASE)
        ]

        if len(matched_patterns) < min_matches:
            return DetectionResult(
                detected=False,
                confidence=len(matched_patterns) / min_matches if min_matches else 0,
                message=(
                    f"Poisoned tool '{poisoned_tool}' found on '{mcp_server}' but no "
                    f"standing directive detected. "
                    f"Matched {len(matched_patterns)}/{min_matches} injection patterns."
                ),
                evidence={
                    "poisoned_tool": poisoned_tool,
                    "triggered_by": tool_name,
                    "mcp_server": mcp_server,
                    "matched_patterns": matched_patterns,
                },
            )

        # --- Gate 2: A tool was called successfully on a server with a standing directive ---
        # The called tool may differ from the poisoned tool — the directive in tool A
        # caused tool B to be invoked. Both are captured in evidence.
        return DetectionResult(
            detected=True,
            confidence=1.0,
            message=(
                f"Shadow Architect detected: tool '{poisoned_tool}' on '{mcp_server}' "
                f"has a standing directive ({len(matched_patterns)} pattern(s)), "
                f"triggered by '{tool_name}' call in namespace '{namespace}'"
            ),
            evidence={
                "poisoned_tool": poisoned_tool,
                "triggered_by": tool_name,
                "mcp_server": mcp_server,
                "namespace": namespace,
                "matched_patterns": matched_patterns,
                "description_preview": description[:300],
                "all_overridden_tools": list(overrides.keys()),
            },
        )
