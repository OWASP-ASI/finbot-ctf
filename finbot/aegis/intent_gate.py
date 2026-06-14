# ============================================================
# File: finbot/aegis/intent_gate.py
# Purpose: Policy-as-code PEP/PDP for pre-execution tool validation
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 3
# OWASP Category: ASI01 Goal Hijack, ASI02 Tool Misuse, ASI05 Unexpected RCE
# ============================================================
"""IntentGate: policy-as-code PEP/PDP for tool hooks."""

import json
import logging
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from finbot.aegis.schemas import (
    PolicyAction,
    PolicyDocument,
    PolicyVerdict,
    ToolInvocationContext,
)
from finbot.config import settings

logger = logging.getLogger(__name__)

_RCE_PATTERNS = (
    re.compile(r"\b(curl|wget|nc|bash|sh)\b", re.I),
    re.compile(r"/etc/(passwd|shadow)", re.I),
    re.compile(r"rm\s+-rf", re.I),
)


class IntentGate:
    """Loads YAML policies and evaluates tool invocations before execution."""

    def __init__(self, policy_dir: Path | None = None) -> None:
        self._policy_dir = policy_dir or Path(settings.AEGIS_POLICY_DIR)
        self._policies: list[PolicyDocument] = []
        self.reload()

    def reload(self) -> None:
        """Reload all YAML policies from the configured directory."""
        self._policies = []
        if not self._policy_dir.exists():
            logger.warning("AEGIS policy dir missing: %s", self._policy_dir)
            return
        for path in sorted(self._policy_dir.glob("*.yaml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                doc = PolicyDocument.model_validate(raw.get("policy", raw))
                self._policies.append(doc)
                logger.info("Loaded AEGIS policy %s v%s", doc.name, doc.version)
            except (ValidationError, yaml.YAMLError) as exc:
                logger.error("Invalid policy %s: %s", path, exc)

    def evaluate_tool(self, ctx: ToolInvocationContext) -> PolicyVerdict:
        """Return allow/deny/quarantine verdict for a tool invocation."""
        for policy in self._policies:
            if policy.allowed_tools and ctx.tool_name not in policy.allowed_tools:
                if not any(ctx.tool_name.endswith(t) for t in policy.allowed_tools):
                    return PolicyVerdict(
                        action=PolicyAction.deny,
                        reason="tool_not_in_allowlist",
                        rule_id=policy.name,
                        asi_tags=["ASI02"],
                    )

        args_blob = json.dumps(ctx.arguments, default=str)
        for pat in _RCE_PATTERNS:
            if pat.search(args_blob) or (
                ctx.tool_description and pat.search(ctx.tool_description)
            ):
                return PolicyVerdict(
                    action=PolicyAction.deny,
                    reason="rce_pattern_blocked",
                    rule_id="builtin_rce",
                    asi_tags=["ASI05"],
                )

        for policy in self._policies:
            for rule in policy.rules:
                if rule.action != PolicyAction.deny:
                    continue
                if rule.condition.startswith("deny_tool:"):
                    denied = rule.condition.split(":", 1)[1]
                    if ctx.tool_name == denied or ctx.tool_name.endswith(denied):
                        return PolicyVerdict(
                            action=PolicyAction.deny,
                            reason=rule.reason,
                            rule_id=rule.id,
                            asi_tags=["ASI02"],
                        )
                if rule.condition == "cross_namespace_tool":
                    ns_arg = str(ctx.arguments.get("namespace", ""))
                    if ns_arg and ns_arg != ctx.namespace:
                        return PolicyVerdict(
                            action=PolicyAction.deny,
                            reason=rule.reason,
                            rule_id=rule.id,
                            asi_tags=["ASI03"],
                        )

        for policy in self._policies:
            for pattern in policy.denied_patterns:
                if re.search(pattern, args_blob, re.I):
                    return PolicyVerdict(
                        action=PolicyAction.deny,
                        reason="denied_pattern_match",
                        rule_id=policy.name,
                        asi_tags=["ASI05"],
                    )

        return PolicyVerdict(action=PolicyAction.allow, reason="default_allow")
