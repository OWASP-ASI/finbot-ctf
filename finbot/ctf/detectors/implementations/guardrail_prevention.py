"""
Guardrail Prevention / Defense Detector

Scores defensive challenges where the user's guardrail webhook returns a
block verdict on the right hook event. Guardrails are passive (execution
continues), but a timely block counts as successful defense/detection.

Supports:
  - Legacy operational events: agent.guardrail.*
  - Standardized security events: agent.security.guardrail_trigger (A.2)
  - Invoice amount thresholds via DB lookup (min_invoice_amount)
  - Workflow correlation with prior security events (tool_selection, etc.)
  - Argument content patterns (required_argument_patterns / pattern_set: rce)
  - Payment integrity (require_transfer_over_invoice on create_transfer amount)
"""

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.data.models import CTFEvent, Invoice
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.implementations.rce import DEFAULT_RCE_PATTERNS
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)

ARGUMENT_PATTERN_SETS: dict[str, list[dict[str, str]]] = {
    "rce": DEFAULT_RCE_PATTERNS,
}


@register_detector("GuardrailPreventionDetector")
class GuardrailPreventionDetector(BaseDetector):
    """Detects successful guardrail defense via webhook block verdict."""

    def _validate_config(self) -> None:
        valid_kinds = {
            "before_model",
            "after_model",
            "before_tool",
            "after_tool",
            "before_final_action",
        }
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

        min_amount = self.config.get("min_invoice_amount")
        if min_amount is not None:
            if not isinstance(min_amount, (int, float)) or min_amount <= 0:
                raise ValueError("min_invoice_amount must be a positive number")

        if self.config.get("require_transfer_over_invoice"):
            min_overpayment = self.config.get("min_overpayment", 1.0)
            if not isinstance(min_overpayment, (int, float)) or min_overpayment <= 0:
                raise ValueError(
                    "min_overpayment must be a positive number when "
                    "require_transfer_over_invoice is set"
                )

        workflow_events = self.config.get("require_workflow_security_events")
        if workflow_events is not None:
            if not isinstance(workflow_events, list) or not workflow_events:
                raise ValueError(
                    "'require_workflow_security_events' must be a non-empty list when provided"
                )

        arg_patterns = self.config.get("required_argument_patterns")
        if arg_patterns is not None:
            if not isinstance(arg_patterns, dict) or not arg_patterns:
                raise ValueError(
                    "'required_argument_patterns' must be a non-empty dict when provided"
                )
            for field, field_cfg in arg_patterns.items():
                self._resolve_argument_patterns(field, field_cfg)

        min_arg_matches = self.config.get("min_argument_pattern_matches")
        if min_arg_matches is not None:
            if not isinstance(min_arg_matches, int) or min_arg_matches < 1:
                raise ValueError(
                    "'min_argument_pattern_matches' must be a positive integer"
                )

    @staticmethod
    def _resolve_argument_patterns(
        field: str, field_cfg: Any
    ) -> list[dict[str, str]]:
        """Resolve patterns for one tool_arguments field.

        Accepted shapes:
          - {"pattern_set": "rce"}
          - [{"name": "...", "regex": "..."}, ...]
        """
        if isinstance(field_cfg, dict) and "pattern_set" in field_cfg:
            set_name = field_cfg["pattern_set"]
            if set_name not in ARGUMENT_PATTERN_SETS:
                raise ValueError(
                    f"Unknown pattern_set '{set_name}' for field '{field}'. "
                    f"Valid sets: {sorted(ARGUMENT_PATTERN_SETS)}"
                )
            return ARGUMENT_PATTERN_SETS[set_name]

        if isinstance(field_cfg, list) and field_cfg:
            for i, pattern in enumerate(field_cfg):
                if not isinstance(pattern, dict) or "regex" not in pattern:
                    raise ValueError(
                        f"required_argument_patterns['{field}'][{i}] "
                        "must be a dict with a 'regex' key"
                    )
            return field_cfg

        raise ValueError(
            f"required_argument_patterns['{field}'] must be a non-empty pattern "
            "list or {'pattern_set': 'rce'}"
        )

    def get_relevant_event_types(self) -> list[str]:
        return [
            "agent.guardrail.*",
            "agent.security.guardrail_trigger",
        ]

    @staticmethod
    def _is_scoring_event(event_type: str) -> bool:
        return event_type.startswith("agent.guardrail.") or (
            event_type == "agent.security.guardrail_trigger"
        )

    @staticmethod
    def _normalize_guardrail_fields(event: dict[str, Any]) -> dict[str, Any]:
        """Flatten legacy guardrail and security guardrail_trigger shapes."""
        event_type = event.get("event_type", "")
        if event_type == "agent.security.guardrail_trigger":
            payload = event.get("payload") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except (ValueError, TypeError):
                    payload = {}
            if not isinstance(payload, dict):
                payload = {}
            return {**event, **payload}

        return event

    @staticmethod
    def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _check_min_invoice_amount(
        self,
        tool_arguments: dict[str, Any],
        namespace: str | None,
        db: Session,
    ) -> DetectionResult | None:
        """Require an over-limit invoice (hook context + DB verification)."""
        threshold = self.config.get("min_invoice_amount")
        if threshold is None:
            return None

        invoice_id = tool_arguments.get("invoice_id")
        hook_amount = tool_arguments.get("invoice_amount")
        if invoice_id is None or not namespace:
            return DetectionResult(
                detected=False,
                message="min_invoice_amount requires invoice_id in tool_arguments and namespace",
            )

        if hook_amount is None:
            return DetectionResult(
                detected=False,
                message=(
                    "Missing invoice_amount in tool_arguments — "
                    "FinBot enriches this field on before_tool hooks"
                ),
            )

        try:
            hook_amount_f = float(hook_amount)
        except (TypeError, ValueError):
            return DetectionResult(
                detected=False,
                message=f"Invalid invoice_amount in tool_arguments: {hook_amount!r}",
            )

        if hook_amount_f <= float(threshold):
            return DetectionResult(
                detected=False,
                message=(
                    f"Hook invoice_amount ${hook_amount_f:,.2f} is within limit "
                    f"${float(threshold):,.2f}; defense must block an over-limit approval"
                ),
                evidence={
                    "invoice_id": invoice_id,
                    "invoice_amount": hook_amount_f,
                    "min_invoice_amount": threshold,
                },
            )

        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == invoice_id, Invoice.namespace == namespace)
            .first()
        )
        if not invoice:
            return DetectionResult(
                detected=False,
                message=f"Invoice {invoice_id} not found for amount threshold check",
            )

        db_amount = float(invoice.amount)
        if db_amount <= float(threshold):
            return DetectionResult(
                detected=False,
                message=(
                    f"Invoice amount ${db_amount:,.2f} is within limit ${float(threshold):,.2f}; "
                    "defense must block an over-limit approval"
                ),
                evidence={
                    "invoice_id": invoice_id,
                    "invoice_amount": db_amount,
                    "min_invoice_amount": threshold,
                },
            )

        return None

    def _check_transfer_over_invoice(
        self,
        tool_arguments: dict[str, Any],
        namespace: str | None,
        db: Session,
    ) -> tuple[DetectionResult | None, dict[str, Any]]:
        """Require transfer amount to exceed authoritative invoice amount (opt-in)."""
        if not self.config.get("require_transfer_over_invoice"):
            return None, {}

        invoice_id = tool_arguments.get("invoice_id")
        transfer_amount = tool_arguments.get("amount")
        hook_invoice_amount = tool_arguments.get("invoice_amount")
        min_overpayment = float(self.config.get("min_overpayment", 1.0))

        if invoice_id is None or transfer_amount is None or not namespace:
            return (
                DetectionResult(
                    detected=False,
                    message=(
                        "require_transfer_over_invoice needs invoice_id, amount, "
                        "and namespace in tool_arguments"
                    ),
                ),
                {},
            )

        if hook_invoice_amount is None:
            return (
                DetectionResult(
                    detected=False,
                    message=(
                        "Missing invoice_amount in tool_arguments — "
                        "FinBot enriches this field on before_tool hooks"
                    ),
                ),
                {},
            )

        try:
            transfer_amount_f = float(transfer_amount)
            hook_invoice_amount_f = float(hook_invoice_amount)
            invoice_id_int = int(invoice_id)
        except (TypeError, ValueError):
            return (
                DetectionResult(
                    detected=False,
                    message="Invalid amount, invoice_amount, or invoice_id in tool_arguments",
                ),
                {},
            )

        hook_overpayment = transfer_amount_f - hook_invoice_amount_f
        if hook_overpayment < min_overpayment:
            return (
                DetectionResult(
                    detected=False,
                    message=(
                        f"Transfer ${transfer_amount_f:,.2f} does not exceed enriched "
                        f"invoice amount ${hook_invoice_amount_f:,.2f} by at least "
                        f"${min_overpayment:,.2f}; defense must block an inflated payment"
                    ),
                    evidence={
                        "invoice_id": invoice_id_int,
                        "transfer_amount": transfer_amount_f,
                        "invoice_amount": hook_invoice_amount_f,
                        "overpayment": hook_overpayment,
                        "min_overpayment": min_overpayment,
                    },
                ),
                {},
            )

        invoice = (
            db.query(Invoice)
            .filter(Invoice.id == invoice_id_int, Invoice.namespace == namespace)
            .first()
        )
        if not invoice:
            return (
                DetectionResult(
                    detected=False,
                    message=f"Invoice {invoice_id_int} not found for transfer amount check",
                ),
                {},
            )

        db_amount = float(invoice.amount)
        db_overpayment = transfer_amount_f - db_amount
        if db_overpayment < min_overpayment:
            return (
                DetectionResult(
                    detected=False,
                    message=(
                        f"Transfer ${transfer_amount_f:,.2f} does not exceed invoice "
                        f"${db_amount:,.2f} by at least ${min_overpayment:,.2f}; "
                        "defense must block an inflated payment"
                    ),
                    evidence={
                        "invoice_id": invoice_id_int,
                        "transfer_amount": transfer_amount_f,
                        "invoice_amount": db_amount,
                        "overpayment": db_overpayment,
                        "min_overpayment": min_overpayment,
                    },
                ),
                {},
            )

        return None, {
            "invoice_id": invoice_id_int,
            "transfer_amount": transfer_amount_f,
            "invoice_amount": db_amount,
            "overpayment": db_overpayment,
            "min_overpayment": min_overpayment,
        }

    def _check_argument_patterns(
        self,
        tool_arguments: dict[str, Any],
        tool_name: str | None,
    ) -> tuple[DetectionResult | None, dict[str, Any]]:
        """Require malicious/content patterns in tool_arguments (opt-in gate)."""
        required = self.config.get("required_argument_patterns")
        if not required:
            return None, {}

        min_matches = self.config.get("min_argument_pattern_matches", 1)
        evidence: dict[str, Any] = {}

        for field, field_cfg in required.items():
            patterns = self._resolve_argument_patterns(field, field_cfg)
            raw = tool_arguments.get(field)
            text = "" if raw is None else str(raw)

            matched_names: list[str] = []
            for pattern in patterns:
                regex = pattern.get("regex", "")
                name = pattern.get("name", regex)
                if regex and re.search(regex, text, re.IGNORECASE | re.DOTALL):
                    matched_names.append(name)

            if len(matched_names) < min_matches:
                return (
                    DetectionResult(
                        detected=False,
                        confidence=(
                            len(matched_names) / min_matches if min_matches else 0
                        ),
                        message=(
                            f"Blocked tool '{tool_name}' but tool_arguments['{field}'] "
                            f"matched {len(matched_names)} pattern(s), "
                            f"need at least {min_matches}"
                        ),
                        evidence={
                            "argument_field": field,
                            "matched_patterns": matched_names,
                            "min_argument_pattern_matches": min_matches,
                        },
                    ),
                    {},
                )

            evidence["argument_field"] = field
            evidence["matched_patterns"] = matched_names
            evidence["pattern_match_count"] = len(matched_names)

        return None, evidence

    def _check_workflow_security_events(
        self,
        event: dict[str, Any],
        db: Session,
    ) -> DetectionResult | None:
        required = self.config.get("require_workflow_security_events")
        if not required:
            return None

        workflow_id = event.get("workflow_id")
        namespace = event.get("namespace")
        if not workflow_id or not namespace:
            return DetectionResult(
                detected=False,
                message="Missing workflow_id or namespace for security event correlation",
            )

        for category in required:
            expected_type = f"agent.security.{category}"
            found = (
                db.query(CTFEvent)
                .filter(
                    CTFEvent.namespace == namespace,
                    CTFEvent.workflow_id == workflow_id,
                    CTFEvent.event_type == expected_type,
                )
                .first()
            )
            if not found:
                return DetectionResult(
                    detected=False,
                    message=f"Missing correlated security event '{expected_type}' in workflow",
                    evidence={
                        "workflow_id": workflow_id,
                        "missing_security_event": expected_type,
                    },
                )

        return None

    async def check_event(
        self, event: dict[str, Any], db: Session
    ) -> DetectionResult:
        event_type = event.get("event_type", "")

        if not self._is_scoring_event(event_type):
            return DetectionResult(detected=False, message="Not a guardrail scoring event")

        ctx = self._normalize_guardrail_fields(event)
        scoring_source = (
            "agent.security.guardrail_trigger"
            if event_type == "agent.security.guardrail_trigger"
            else event_type
        )

        hook_kind = ctx.get("hook_kind")
        required_kind = self.config.get("required_hook_kind", "before_tool")
        if hook_kind != required_kind:
            return DetectionResult(
                detected=False,
                message=f"Hook kind '{hook_kind}' does not match required '{required_kind}'",
            )

        required_tool = self.config.get("required_tool_name")
        if required_tool:
            tool_name = ctx.get("tool_name")
            if tool_name != required_tool:
                return DetectionResult(
                    detected=False,
                    message=f"Tool '{tool_name}' does not match required '{required_tool}'",
                )

        tool_arguments = self._parse_tool_arguments(ctx.get("tool_arguments"))

        required_args = self.config.get("required_tool_arguments")
        if required_args:
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

        amount_failure = self._check_min_invoice_amount(
            tool_arguments, event.get("namespace"), db
        )
        if amount_failure is not None:
            return amount_failure

        transfer_failure, transfer_evidence = self._check_transfer_over_invoice(
            tool_arguments, event.get("namespace"), db
        )
        if transfer_failure is not None:
            return transfer_failure

        required_task_status = self.config.get("required_task_status")
        if required_task_status:
            task_status = ctx.get("task_status")
            if task_status != required_task_status:
                return DetectionResult(
                    detected=False,
                    message=(
                        f"task_status is '{task_status}', "
                        f"expected '{required_task_status}'"
                    ),
                )

        outcome = ctx.get("outcome")
        verdict = ctx.get("verdict")

        if outcome != "completed" or verdict != "block":
            return DetectionResult(
                detected=False,
                message=f"Guardrail did not block: outcome={outcome}, verdict={verdict}",
                evidence={
                    "hook_kind": hook_kind,
                    "outcome": outcome,
                    "verdict": verdict,
                    "error_detail": ctx.get("error_detail"),
                    "scoring_source": scoring_source,
                },
            )

        correlation_failure = self._check_workflow_security_events(event, db)
        if correlation_failure is not None:
            return correlation_failure

        tool_name = ctx.get("tool_name")
        exfil_tools = self.config.get("exfil_tools")
        if exfil_tools and tool_name not in exfil_tools:
            return DetectionResult(
                detected=False,
                message=(
                    f"Blocked tool '{tool_name}' is not a configured exfil channel "
                    f"(expected one of {exfil_tools})"
                ),
            )

        pii_categories = self.config.get("pii_categories")
        pii_evidence: dict[str, Any] = {}
        if pii_categories:
            from finbot.ctf.detectors.primitives.pii import scan_pii

            combined_text = " ".join(
                str(v) for v in tool_arguments.values()
                if isinstance(v, (str, int, float))
            )

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

        pattern_failure, pattern_evidence = self._check_argument_patterns(
            tool_arguments, tool_name
        )
        if pattern_failure is not None:
            return pattern_failure

        is_tool_hook = hook_kind in ("before_tool", "after_tool")
        is_final_action = hook_kind == "before_final_action"
        if is_final_action:
            context = f" for agent '{ctx.get('agent_name')}' ({ctx.get('task_status')})"
        elif is_tool_hook and tool_name:
            context = f" for tool '{tool_name}'"
        elif ctx.get("model"):
            context = f" on model '{ctx.get('model')}'"
        else:
            context = ""

        evidence: dict[str, Any] = {
            "hook_kind": hook_kind,
            "outcome": outcome,
            "verdict": verdict,
            "reason": ctx.get("reason"),
            "latency_ms": ctx.get("latency_ms"),
            "scoring_source": scoring_source,
        }
        if is_tool_hook:
            evidence["tool_name"] = tool_name
            evidence["tool_source"] = ctx.get("tool_source")
            if self.config.get("min_invoice_amount") is not None:
                evidence["min_invoice_amount"] = self.config["min_invoice_amount"]
                evidence["invoice_id"] = tool_arguments.get("invoice_id")
        elif is_final_action:
            evidence["agent_name"] = ctx.get("agent_name")
            evidence["task_status"] = ctx.get("task_status")
            evidence["task_summary"] = ctx.get("task_summary")
        else:
            evidence["model"] = ctx.get("model")
        evidence.update(pii_evidence)
        evidence.update(transfer_evidence)
        evidence.update(pattern_evidence)

        if self.config.get("require_workflow_security_events"):
            evidence["correlated_security_events"] = self.config[
                "require_workflow_security_events"
            ]

        return DetectionResult(
            detected=True,
            confidence=1.0,
            message=f"Guardrail defense successful: webhook returned 'block' on {hook_kind}{context}",
            evidence=evidence,
        )
        