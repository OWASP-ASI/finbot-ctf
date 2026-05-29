"""Tool Drift Detector

Detects when MCP tool definitions have been modified from their expected state,
indicating potential tool poisoning. Supports two complementary detection modes:

1. Override detection: Checks if MCPServerConfig has tool_overrides applied
2. Baseline comparison: Compares discovered descriptions against known-good baselines

Both modes run simultaneously when configured. Exports a reusable
``check_tool_drift()`` function for composition in higher-level detectors.
"""

import logging
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.data.models import MCPServerConfig
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


def check_tool_drift(
    discovered_descriptions: dict[str, str],
    baseline_descriptions: dict[str, str] | None = None,
    overrides: dict[str, Any] | None = None,
    tool_names: list[str] | None = None,
) -> dict[str, Any]:
    """Check for tool definition drift against baselines and/or overrides.

    Args:
        discovered_descriptions: Tool name → description as reported by the MCP server.
        baseline_descriptions: Known-good descriptions to diff against (optional).
        overrides: Parsed ``tool_overrides_json`` from MCPServerConfig (optional).
        tool_names: Limit checking to these tool names. If *None*, the union of
            all keys from *discovered_descriptions* and *baseline_descriptions*
            is used.

    Returns:
        Dict with ``drifted`` (bool), ``drifted_tools`` (list of detail dicts),
        and ``checked_count`` (int).
    """
    scope = tool_names or sorted(
        set(list(discovered_descriptions.keys()) + list((baseline_descriptions or {}).keys()))
    )

    drifted_tools: list[dict[str, Any]] = []

    for tool_name in scope:
        drift_info: dict[str, Any] = {"tool_name": tool_name}
        reasons: list[str] = []

        if overrides and tool_name in overrides:
            override_entry = overrides[tool_name]
            if isinstance(override_entry, dict) and override_entry.get("description"):
                reasons.append("tool_override_applied")
                drift_info["override_description"] = override_entry["description"][:200]

        if baseline_descriptions and tool_name in baseline_descriptions:
            baseline = baseline_descriptions[tool_name]
            discovered = discovered_descriptions.get(tool_name, "")
            if baseline != discovered:
                similarity = SequenceMatcher(None, baseline, discovered).ratio()
                reasons.append("description_changed")
                drift_info["similarity"] = round(similarity, 3)
                drift_info["baseline_preview"] = baseline[:200]
                drift_info["discovered_preview"] = discovered[:200]

        if tool_name in (baseline_descriptions or {}) and tool_name not in discovered_descriptions:
            reasons.append("tool_missing")

        if reasons:
            drift_info["reasons"] = reasons
            drifted_tools.append(drift_info)

    return {
        "drifted": len(drifted_tools) > 0,
        "drifted_tools": drifted_tools,
        "checked_count": len(scope),
    }


@register_detector("ToolDriftDetector")
class ToolDriftDetector(BaseDetector):
    """Detects tool definition drift / poisoning on an MCP server.

    Configuration:
        mcp_server: str - MCP server to monitor (required)
        tool_names: list[str] - Specific tools to check (optional; all tools if omitted)
        baseline_descriptions: dict[str, str] - Known-good descriptions keyed by
            tool name (optional; if omitted only override detection is used)

    Example YAML:
        detector_class: ToolDriftDetector
        detector_config:
          mcp_server: finstripe
          tool_names:
            - create_transfer
            - get_balance
          baseline_descriptions:
            create_transfer: "Initiate a fund transfer to the specified vendor account."
    """

    def _validate_config(self) -> None:
        if "mcp_server" not in self.config:
            raise ValueError("ToolDriftDetector requires 'mcp_server'")

    def get_relevant_event_types(self) -> list[str]:
        return ["agent.*.mcp_tools_discovered"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        target_server = self.config["mcp_server"]
        event_server = event.get("mcp_server", "")

        if event_server != target_server:
            return DetectionResult(
                detected=False,
                message=f"Server mismatch: watching '{target_server}', got '{event_server}'",
            )

        tool_names: list[str] | None = self.config.get("tool_names")
        baseline_descriptions: dict[str, str] | None = self.config.get("baseline_descriptions")
        discovered_descriptions: dict[str, str] = event.get("tool_descriptions", {})
        namespace = event.get("namespace")

        overrides: dict[str, Any] = {}
        if namespace:
            server_config = (
                db.query(MCPServerConfig)
                .filter(
                    MCPServerConfig.namespace == namespace,
                    MCPServerConfig.server_type == target_server,
                )
                .first()
            )
            if server_config:
                overrides = server_config.get_tool_overrides()

        result = check_tool_drift(
            discovered_descriptions=discovered_descriptions,
            baseline_descriptions=baseline_descriptions,
            overrides=overrides,
            tool_names=tool_names,
        )

        if not result["drifted"]:
            return DetectionResult(
                detected=False,
                message=(
                    f"No tool drift on '{target_server}' "
                    f"({result['checked_count']} tools checked)"
                ),
            )

        drifted_names = [t["tool_name"] for t in result["drifted_tools"]]
        all_reasons: set[str] = set()
        for t in result["drifted_tools"]:
            all_reasons.update(t.get("reasons", []))

        return DetectionResult(
            detected=True,
            confidence=1.0,
            message=(
                f"Tool drift detected on '{target_server}': "
                f"{drifted_names} ({', '.join(sorted(all_reasons))})"
            ),
            evidence={
                "mcp_server": target_server,
                "drifted_tools": result["drifted_tools"],
                "checked_count": result["checked_count"],
            },
        )
