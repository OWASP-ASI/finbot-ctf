"""Sequence Detector

Detects multi-step attack patterns across a session or workflow window.
Challenge authors configure this in YAML with no Python required.
"""

import fnmatch
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any, NotRequired, TypedDict

from sqlalchemy.orm import Session

from finbot.core.data.models import CTFEvent
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)

# Known CTFEvent column names available for condition matching.
# Defined at module level to avoid rebuilding the frozenset on every
# _matches_step call (which runs once per event × once per step).
_CTF_COLUMNS: frozenset[str] = frozenset({
    "event_type", "event_category", "event_subtype",
    "session_id", "workflow_id", "namespace", "user_id",
    "vendor_id", "agent_name", "tool_name", "severity",
})


class StepSpec(TypedDict):
    event_type: str          # Glob pattern, e.g. "agent.*.tool_call_success"
    label: str               # Human-readable name for evidence output
    conditions: NotRequired[dict[str, Any]]  # ToolCallDetector operators


@register_detector("SequenceDetector")
class SequenceDetector(BaseDetector):
    """Detects multi-step attack patterns across a session window.

    Configuration:
        steps: list[StepSpec]      -- ordered sequence to match
        within_n_events: int       -- history window size: load latest N events for the session/workflow (default: unlimited)
        within_seconds: int        -- optional time-based window (default: unlimited)
        order_matters: bool        -- enforce step ordering (default: true)
        window: "session" | "workflow"  -- scope for history query (default: "session")

    StepSpec fields:
        event_type: str   -- glob pattern, e.g. "agent.*.tool_call_success"
        conditions: dict  -- field conditions using ToolCallDetector operators
        label: str        -- human-readable name for evidence output

    Example YAML:
        detector_class: SequenceDetector
        detector_config:
          steps:
            - event_type: "agent.*.tool_call_success"
              conditions: { tool_name: "approve_invoice" }
              label: "First micro-payment"
            - event_type: "agent.*.tool_call_success"
              conditions: { tool_name: "approve_invoice" }
              label: "Second micro-payment"
          within_n_events: 50
          within_seconds: 300
          order_matters: true
          window: "session"
    """

    def _validate_config(self) -> None:
        steps = self.config.get("steps")
        if not steps or not isinstance(steps, list):
            raise ValueError("SequenceDetector requires 'steps' as a non-empty list")
        for i, step in enumerate(steps):
            if "event_type" not in step:
                raise ValueError(f"Step {i} missing required 'event_type'")
            if "label" not in step:
                raise ValueError(f"Step {i} missing required 'label'")
        window = self.config.get("window", "session")
        if window not in ("session", "workflow"):
            raise ValueError("window must be 'session' or 'workflow'")

    def get_relevant_event_types(self) -> list[str]:
        steps: list[StepSpec] = self.config.get("steps", [])
        return [step["event_type"] for step in steps]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        steps: list[StepSpec] = self.config.get("steps", [])
        within_n = self.config.get("within_n_events")
        within_seconds = self.config.get("within_seconds")
        order_matters = self.config.get("order_matters", True)
        window = self.config.get("window", "session")

        namespace = event.get("namespace")

        if window == "workflow":
            window_id = event.get("workflow_id")
            if not window_id:
                return DetectionResult(detected=False, message="No workflow_id in event")
            filter_col = CTFEvent.workflow_id
        else:
            window_id = event.get("session_id")
            if not window_id:
                return DetectionResult(detected=False, message="No session_id in event")
            filter_col = CTFEvent.session_id

        query = db.query(CTFEvent).filter(
            CTFEvent.namespace == namespace,
            filter_col == window_id,
        )

        if within_seconds is not None:
            event_time = event.get("timestamp")
            if isinstance(event_time, str):
                try:
                    event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
                except ValueError:
                    return DetectionResult(
                        detected=False,
                        message="within_seconds set but event timestamp is invalid",
                    )
            elif not isinstance(event_time, datetime):
                return DetectionResult(
                    detected=False,
                    message="within_seconds set but event has no timestamp",
                )
            cutoff = event_time - timedelta(seconds=within_seconds)
            query = query.filter(CTFEvent.timestamp >= cutoff)

        if within_n is not None:
            history = (
                query.order_by(CTFEvent.timestamp.desc())
                .limit(within_n)
                .all()
            )
            history = list(reversed(history))
        else:
            history = query.order_by(CTFEvent.timestamp.asc()).all()

        matched: list[dict[str, Any]] = []
        search_from = 0
        consumed: set[int] = set()  # indices already claimed by a previous step

        for step in steps:
            found_at = None
            start = search_from if order_matters else 0
            for i in range(start, len(history)):
                if i in consumed:
                    continue
                if self._matches_step(history[i], step):
                    found_at = i
                    break

            if found_at is None:
                return DetectionResult(
                    detected=False,
                    message=f"Sequence incomplete: step '{step['label']}' not matched",
                    evidence={
                        "matched_steps": matched,
                        "missing_step": step["label"],
                        "window": window,
                        "window_id": window_id,
                    },
                )

            matched.append(
                {
                    "step": step["label"],
                    "event_id": history[found_at].id,
                    "event_type": history[found_at].event_type,
                }
            )
            consumed.add(found_at)
            if order_matters:
                search_from = found_at + 1

        return DetectionResult(
            detected=True,
            confidence=1.0,
            message=f"Multi-step sequence detected: {[m['step'] for m in matched]}",
            evidence={
                "matched_steps": matched,
                "window": window,
                "window_id": window_id,
                "step_count": len(matched),
            },
        )

    def _matches_step(self, ctf_event: CTFEvent, step: StepSpec) -> bool:
        """Check if a CTFEvent matches a step spec."""
        if not fnmatch.fnmatch(ctf_event.event_type, step["event_type"]):
            return False

        conditions = step.get("conditions", {})
        if not conditions:
            return True

        details: dict[str, Any] = {}
        if ctf_event.details:
            try:
                details = json.loads(ctf_event.details)
            except (json.JSONDecodeError, TypeError):
                pass

        for field, condition in conditions.items():
            # Prefer JSON details; fall back to model columns for known fields
            if field in details:
                actual = details[field]
            elif field in _CTF_COLUMNS:
                actual = getattr(ctf_event, field, None)
            else:
                actual = None
            if not self._check_condition(actual, condition):
                return False

        return True

    def _check_condition(self, actual: Any, condition: Any) -> bool:
        """Check if actual value satisfies condition (ToolCallDetector operators).

        Multiple operators in one condition dict are ANDed together, so
        {'gte': 10, 'lte': 20} passes only when 10 <= actual <= 20.
        """
        if not isinstance(condition, dict):
            return actual == condition

        for operator, expected in condition.items():
            op = operator.lower()
            if op == "exists":
                if not ((actual is not None) == expected):
                    return False
            elif actual is None:
                return False
            elif op in ("equals", "eq"):
                if actual != expected:
                    return False
            elif op == "in":
                if actual not in expected:
                    return False
            elif op == "not_in":
                if actual in expected:
                    return False
            elif op == "contains":
                if expected.lower() not in str(actual).lower():
                    return False
            elif op == "gt":
                if not float(actual) > float(expected):
                    return False
            elif op == "gte":
                if not float(actual) >= float(expected):
                    return False
            elif op == "lt":
                if not float(actual) < float(expected):
                    return False
            elif op == "lte":
                if not float(actual) <= float(expected):
                    return False
            elif op == "matches":
                if not re.fullmatch(expected, str(actual), re.IGNORECASE):
                    return False
            else:
                logger.warning(
                    "Unknown condition operator %r — treating as no-match", op
                )
                return False

        return True
