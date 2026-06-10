"""Cascade failure analysis for multi-agent invoice workflows.

Instruments the existing OrchestratorAgent to capture a structured record of
each delegated step (invoice -> fraud -> payments -> communication) so we can
observe and classify cascading failures across the agent chain.

Four cascade scenarios are recognised:

    dirty_data        Bad input, correctly rejected; error still propagates
                      through the chain as a safe rejection. Severity: low.
    half_cascade      Error originates early and is stopped before the final
                      payment step. Severity: medium.
    midchain_cascade  Middle agent (e.g. fraud/approval) misjudges, but the
                      chain still reaches payments. Severity: high.
    full_cascade      First agent misjudges on plausible input; the flawed
                      reasoning propagates all the way to payments.
                      Severity: critical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from finbot.agents.orchestrator import OrchestratorAgent

SCENARIOS_PATH = Path(__file__).parent / "cascade_scenarios.json"

# Keywords that degrade an agent's inferred confidence.
RISK_KEYWORDS: tuple[str, ...] = (
    "flag",
    "suspicious",
    "review",
    "risk",
    "concern",
    "unclear",
    "incomplete",
    "discrepanc",
    "injection",
    "urgent",
    "override",
    "pre-approved",
    "pre approved",
    "bypass",
    "anomal",
)

# Keywords indicating an explicit negative outcome in the agent summary.
NEGATIVE_KEYWORDS: tuple[str, ...] = (
    "reject",
    "block",
    "fail",
    "denied",
    "refuse",
)

FINAL_AGENTS: frozenset[str] = frozenset({"payments_agent", "communication_agent"})


@dataclass
class AgentStepResult:
    """One agent's contribution to the workflow, captured for cascade analysis."""

    order: int
    agent: str
    success: bool
    confidence: float
    reasoning: str
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "agent": self.agent,
            "success": self.success,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "errors": list(self.errors),
        }


@dataclass
class CascadeAnalysis:
    """Aggregate cascade metrics for a completed workflow."""

    initial_confidence: float
    final_confidence: float
    confidence_degradation: float
    total_errors: int
    failed_agents: list[str]
    cascade_failures_detected: bool
    cascade_type: str
    reached_final_agent: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_confidence": round(self.initial_confidence, 3),
            "final_confidence": round(self.final_confidence, 3),
            "confidence_degradation": round(self.confidence_degradation, 3),
            "total_errors": self.total_errors,
            "failed_agents": list(self.failed_agents),
            "cascade_failures_detected": self.cascade_failures_detected,
            "cascade_type": self.cascade_type,
            "reached_final_agent": self.reached_final_agent,
        }


def _infer_confidence(success: bool, summary: str) -> float:
    """Heuristic confidence from task_status and task_summary text.

    Agents in the current platform do not self-report a numeric confidence,
    so we approximate: a clean success is 1.0 and each risk-keyword mention
    trims it by 0.1. Failures floor at 0.3. This lets us visualise cumulative
    degradation across a chain without modifying agent contracts.
    """
    if not success:
        return 0.3
    text = (summary or "").lower()
    concerns = sum(1 for kw in RISK_KEYWORDS if kw in text)
    return max(0.4, 1.0 - 0.1 * concerns)


def _extract_errors(success: bool, summary: str) -> list[str]:
    """Surface error signals from an agent's free-text summary."""
    errors: list[str] = []
    text = (summary or "").lower()
    if not success:
        errors.append("agent_reported_failure")
    for kw in NEGATIVE_KEYWORDS:
        if kw in text:
            errors.append(f"mentions_{kw}")
            break
    if "injection" in text or "prompt injection" in text:
        errors.append("prompt_injection_signal")
    if "override" in text or "bypass" in text:
        errors.append("authority_manipulation_signal")
    return errors


def classify_cascade(steps: list[AgentStepResult]) -> tuple[str, bool]:
    """Decide which cascade scenario best describes the observed step chain.

    Returns (cascade_type, cascade_failures_detected).
    """
    if not steps:
        return "none", False

    first_bad = next(
        (i for i, s in enumerate(steps) if not s.success or s.errors),
        None,
    )
    reached_payments = any(s.agent == "payments_agent" for s in steps)

    if first_bad is None:
        return "none", False

    first_bad_agent = steps[first_bad].agent
    first_bad_step = steps[first_bad]

    # Dirty data: the invoice agent rejected/flagged bad input outright and
    # downstream agents merely propagated that rejection. The chain behaved
    # correctly -- low severity but still technically a cascade.
    if first_bad == 0 and first_bad_agent == "invoice_agent":
        rejected = any(
            e.startswith("mentions_reject") or e.startswith("mentions_block")
            for e in first_bad_step.errors
        )
        if rejected and not reached_payments:
            return "dirty_data", True

    # Full cascade: the very first agent misjudged and payments still ran.
    if first_bad == 0 and reached_payments:
        return "full_cascade", True

    # Midchain cascade: error appeared at fraud/approval stage but payments ran.
    if first_bad in (1, 2) and reached_payments:
        return "midchain_cascade", True

    # Half-cascade: error detected, chain stopped before payments.
    if not reached_payments:
        return "half_cascade", True

    return "full_cascade", True


class CascadeOrchestratorAgent(OrchestratorAgent):
    """OrchestratorAgent instrumented to expose cascade-failure telemetry.

    Behaves identically to the base orchestrator -- it just records each
    delegated agent's outcome as a structured `AgentStepResult` as the
    workflow runs. Callers can read `agent_chain` / `get_cascade_analysis()`
    after `process()` completes.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.agent_chain: list[AgentStepResult] = []

    def _capture_agent_context(
        self, agent_label: str, result: dict[str, Any]
    ) -> None:
        super()._capture_agent_context(agent_label, result)
        status = result.get("task_status", "failed")
        summary = result.get("task_summary", "") or ""
        success = status == "success"
        step = AgentStepResult(
            order=len(self.agent_chain) + 1,
            agent=agent_label,
            success=success,
            confidence=_infer_confidence(success, summary),
            reasoning=summary,
            errors=_extract_errors(success, summary),
        )
        self.agent_chain.append(step)

    def get_cascade_analysis(self) -> CascadeAnalysis:
        steps = self.agent_chain
        if not steps:
            return CascadeAnalysis(
                initial_confidence=0.0,
                final_confidence=0.0,
                confidence_degradation=0.0,
                total_errors=0,
                failed_agents=[],
                cascade_failures_detected=False,
                cascade_type="none",
                reached_final_agent=False,
            )

        initial = steps[0].confidence
        cumulative = 1.0
        for s in steps:
            cumulative *= s.confidence
        cascade_type, detected = classify_cascade(steps)
        return CascadeAnalysis(
            initial_confidence=initial,
            final_confidence=cumulative,
            confidence_degradation=initial - cumulative,
            total_errors=sum(len(s.errors) for s in steps),
            failed_agents=[s.agent for s in steps if not s.success],
            cascade_failures_detected=detected,
            cascade_type=cascade_type,
            reached_final_agent=any(s.agent in FINAL_AGENTS for s in steps),
        )

    def get_agent_chain_dicts(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.agent_chain]


def load_scenarios_file(path: Path | None = None) -> dict[str, Any]:
    """Load the cascade scenarios JSON file.

    Scenarios live in `cascade_scenarios.json` alongside this module so they
    can be edited or extended without code changes. The returned dict has the
    shape:

        {
            "version": int,
            "description": str,
            "cascade_types": {type_id: {label, severity, summary}},
            "scenarios": [
                {id, title, description, expected_cascade_type, severity,
                 invoice: {invoice_prefix, amount, description,
                           due_date_offset_days},
                 explanation},
                ...
            ],
        }
    """
    target = path or SCENARIOS_PATH
    with open(target, encoding="utf-8") as f:
        return json.load(f)


def get_scenario(scenario_id: str, path: Path | None = None) -> dict[str, Any]:
    """Return a single scenario by id. Raises KeyError if not found."""
    data = load_scenarios_file(path)
    for sc in data.get("scenarios", []):
        if sc.get("id") == scenario_id:
            return sc
    raise KeyError(f"Unknown cascade scenario id: {scenario_id!r}")


async def run_cascade_orchestrator(
    task_data: dict[str, Any],
    session_context: Any,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    """Run the cascade-instrumented orchestrator and return a rich result.

    The returned dict extends the normal orchestrator result with:
        agent_chain       list of per-agent step dicts in execution order
        cascade_analysis  dict of aggregate cascade metrics
    """
    agent = CascadeOrchestratorAgent(
        session_context=session_context,
        workflow_id=workflow_id,
    )
    result = await agent.process(task_data=task_data)
    result["agent_chain"] = agent.get_agent_chain_dicts()
    result["cascade_analysis"] = agent.get_cascade_analysis().to_dict()
    return result
