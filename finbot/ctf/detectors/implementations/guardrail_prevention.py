"""
Guardrail Prevention Detector

Labs-only detector for guardrail challenges where the user's webhook
must successfully **block** a specific hook event. Works for both tool
hooks (e.g. block a dangerous tool call) and model hooks (e.g. block
model output containing sensitive data).

Detection logic:
  1. Match guardrail webhook events (agent.guardrail.*)
  2. Check the hook_kind matches the required hook kind
  3. Optionally filter by tool_name (tool hooks only)
  4. Optionally verify required key-value pairs in tool_arguments
  5. If exfil_tools is configured, verify the tool is an exfil channel
  6. If pii_categories is configured, verify tool_arguments contain PII
  7. If outcome is "completed" and verdict is "block" -> detected
  8. Timeout / error / invalid_verdict -> not detected (guardrail failed)

Configuration:
  required_hook_kind: str — hook kind that must produce a block verdict.
      One of: before_model, after_model, before_tool, after_tool.
      Default: "before_tool"
  required_tool_name: str | None — if set, only match events for this
      specific tool (tool hooks only). Default: None (any)
  required_tool_arguments: dict[str, Any] | None — if set, each key-value
      pair must be present in the event's tool_arguments for the block to
      count. Example: {"status": "approved"}. Default: None (no check)
  exfil_tools: list[str] | None — if set, the blocked tool must be one
      of these (namespaced, e.g. "systemutils__network_request").
      Default: None (any tool counts)
  pii_categories: list[str] | None — if set, tool_arguments must contain
      PII from these categories for the block to count.
      Default: None (no PII check)
  min_pii_matches: int — minimum PII matches required. Default: 1.
"""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


@register_detector("GuardrailPreventionDetector")
class GuardrailPreventionDetector(BaseDetector):
    """Detects successful guardrail prevention via webhook block verdict.

    When exfil_tools and pii_categories are configured, the detector
    validates that the blocked tool call was a genuine exfiltration
    attempt — not just a blanket block on every tool call.
    """

    def _validate_config(self) -> None:
        valid_kinds = {"before_model", "after_model", "before_tool", "after_tool"}
        kind = self.config.get("required_hook_kind", "before_tool")
        if kind not in valid_kinds:
            raise ValueError(
                f"required_hook_kind must be one of {valid_kinds}, got '{kind}'"
            )

        pii_categories = self.config.get("pii_categories")
        if pii_categories is not None:
            from finbot.ctf.detectors.primitives.pii import PII_CATEGORIES

            if not isinstance(pii_categories, list) or not pii_categories:
                raise ValueError("'pii_categories' must be a non-empty list when provided")
            unknown = set(pii_categories) - set(PII_CATEGORIES.keys())
            if unknown:
                raise ValueError(
                    f"Unknown PII categories: {unknown}. "
                    f"Valid categories: {sorted(PII_CATEGORIES.keys())}"
                )

        required_args = self.config.get("required_tool_arguments")
        if required_args is not None:
            if not isinstance(required_args, dict) or not required_args:
                raise ValueError(
                    "'required_tool_arguments' must be a non-empty dict when provided"
                )

        exfil_tools = self.config.get("exfil_tools")
        if exfil_tools is not None:
            if not isinstance(exfil_tools, list) or not exfil_tools:
                raise ValueError("'exfil_tools' must be a non-empty list when provided")

    def get_relevant_event_types(self) -> list[str]:
        return ["agent.guardrail.*"]

    async def check_event(
        self, event: dict[str, Any], db: Session
    ) -> DetectionResult:
        event_type = event.get("event_type", "")

        if not event_type.startswith("agent.guardrail."):
            return DetectionResult(detected=False, message="Not a guardrail event")

        hook_kind = event.get("hook_kind")
        required_kind = self.config.get("required_hook_kind", "before_tool")
        if hook_kind != required_kind:
            return DetectionResult(
                detected=False,
                message=f"Hook kind '{hook_kind}' does not match required '{required_kind}'",
            )

        required_tool = self.config.get("required_tool_name")
        if required_tool:
            tool_name = event.get("tool_name")
            if tool_name != required_tool:
                return DetectionResult(
                    detected=False,
                    message=f"Tool '{tool_name}' does not match required '{required_tool}'",
                )

        # --- Tool arguments gate (optional) ---
        required_args = self.config.get("required_tool_arguments")
        if required_args:
            tool_arguments = event.get("tool_arguments", {})
            if isinstance(tool_arguments, str):
                try:
                    tool_arguments = json.loads(tool_arguments)
                except (ValueError, TypeError):
                    tool_arguments = {}
            if not isinstance(tool_arguments, dict):
                tool_arguments = {}

            for key, expected in required_args.items():
                actual = tool_arguments.get(key)
                if actual != expected:
                    return DetectionResult(
                        detected=False,
                        message=(
                            f"tool_arguments['{key}'] is '{actual}', "
                            f"expected '{expected}'"
                        ),
                    )

        outcome = event.get("outcome")
        verdict = event.get("verdict")

        if outcome != "completed" or verdict != "block":
            return DetectionResult(
                detected=False,
                message=f"Guardrail did not block: outcome={outcome}, verdict={verdict}",
                evidence={
                    "hook_kind": hook_kind,
                    "outcome": outcome,
                    "verdict": verdict,
                    "error_detail": event.get("error_detail"),
                },
            )

        # --- Exfil tool gate (optional) ---
        tool_name = event.get("tool_name")
        exfil_tools = self.config.get("exfil_tools")
        if exfil_tools and tool_name not in exfil_tools:
            return DetectionResult(
                detected=False,
                message=(
                    f"Blocked tool '{tool_name}' is not a configured exfil channel "
                    f"(expected one of {exfil_tools})"
                ),
            )

        # --- PII gate (optional) ---
        pii_categories = self.config.get("pii_categories")
        pii_evidence: dict[str, Any] = {}
        if pii_categories:
            from finbot.ctf.detectors.primitives.pii import scan_pii

            tool_arguments = event.get("tool_arguments", {})
            if isinstance(tool_arguments, str):
                try:
                    tool_arguments = json.loads(tool_arguments)
                except (ValueError, TypeError):
                    tool_arguments = {}

            combined_text = " ".join(
                str(v) for v in tool_arguments.values()
                if isinstance(v, (str, int, float))
            ) if isinstance(tool_arguments, dict) else str(tool_arguments)

            min_pii = self.config.get("min_pii_matches", 1)
            pii_matches = scan_pii(combined_text, categories=pii_categories)

            if len(pii_matches) < min_pii:
                return DetectionResult(
                    detected=False,
                    confidence=len(pii_matches) / min_pii if min_pii else 0,
                    message=(
                        f"Blocked tool '{tool_name}' but tool_arguments contain "
                        f"{len(pii_matches)} PII match(es), need at least {min_pii}"
                    ),
                )

            categories_found = sorted({m.category for m in pii_matches})
            pii_evidence = {
                "pii_categories_found": categories_found,
                "pii_match_count": len(pii_matches),
                "pii_matches": [m.to_dict() for m in pii_matches],
            }

        # --- All gates passed ---
        is_tool_hook = hook_kind in ("before_tool", "after_tool")
        context = (
            f" for tool '{tool_name}'"
            if is_tool_hook and tool_name
            else f" on model '{event.get('model')}'"
            if event.get("model")
            else ""
        )

        evidence: dict[str, Any] = {
            "hook_kind": hook_kind,
            "outcome": outcome,
            "verdict": verdict,
            "reason": event.get("reason"),
            "latency_ms": event.get("latency_ms"),
        }
        if is_tool_hook:
            evidence["tool_name"] = tool_name
            evidence["tool_source"] = event.get("tool_source")
        else:
            evidence["model"] = event.get("model")
        evidence.update(pii_evidence)

        return DetectionResult(
            detected=True,
            confidence=1.0,
            message=f"Guardrail prevention successful: webhook returned 'block' on {hook_kind}{context}",
            evidence=evidence,
        )
