"""
Sequence Detector Primitive

Detects multi-step attack patterns across a session or workflow window.
Unlike all existing detectors (which fire on a single event), this primitive
queries CTFEvent history to match an ordered sequence of steps.

Challenge authors configure sequences in YAML — no Python required.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


class StepSpec:
    """A single step in an attack sequence.

    Attributes:
        event_type: Glob pattern matched against CTFEvent.event_type
                    e.g. "agent.*.tool_call_success"
        conditions: Field conditions checked against the event's details dict
                    e.g. {"tool_name": "approve_invoice"}
        label:      Human-readable name shown in evidence output
    """

    def __init__(self, event_type: str, conditions: dict[str, Any], label: str):
        self.event_type = event_type
        self.conditions = conditions
        self.label = label

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StepSpec":
        return cls(
            event_type=d["event_type"],
            conditions=d.get("conditions", {}),
            label=d.get("label", d["event_type"]),
        )


class SequenceDetector(BaseDetector):
    """Detects multi-step attack patterns across a session window.

    Configuration (set via YAML detector_config):
        steps:           list[StepSpec]  — ordered sequence to match (required)
        within_n_events: int             — max events between steps (default: unlimited)
        within_seconds:  int             — optional time-based window (default: None)
        order_matters:   bool            — enforce step ordering (default: True)
        window:          str             — "session" | "workflow" (default: "session")
    """

    def _validate_config(self) -> None:
        if not self.config.get("steps"):
            raise ValueError("SequenceDetector requires at least one step in config")

        window = self.config.get("window", "session")
        if window not in ("session", "workflow"):
            raise ValueError(f"window must be 'session' or 'workflow', got: {window!r}")

        within_n = self.config.get("within_n_events")
        if within_n is not None and (not isinstance(within_n, int) or within_n < 1):
            raise ValueError("within_n_events must be a positive integer")

        within_s = self.config.get("within_seconds")
        if within_s is not None and (not isinstance(within_s, int) or within_s < 1):
            raise ValueError("within_seconds must be a positive integer")

    def _get_steps(self) -> list[StepSpec]:
        return [StepSpec.from_dict(s) for s in self.config["steps"]]

    def get_relevant_event_types(self) -> list[str]:
        return [step["event_type"] for step in self.config.get("steps", [])]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if the incoming event completes a configured attack sequence.

        Steps:
          1. Determine the window scope (session_id or workflow_id)
          2. Query CTFEvent history for that scope
          3. Walk configured steps and match against history in order
          4. Fire only if all steps matched within the configured window
        """
        raise NotImplementedError("check_event will be implemented in the next step")

    # ------------------------------------------------------------------
    # Private helpers (stubs — to be filled in next)
    # ------------------------------------------------------------------

    def _query_history(
        self, db: Session, namespace: str, scope_field: str, scope_value: str
    ) -> list[dict[str, Any]]:
        """Query CTFEvent history for the window scope, ordered by timestamp asc.

        Args:
            db:          SQLAlchemy session
            namespace:   tenant namespace
            scope_field: "session_id" or "workflow_id"
            scope_value: the actual id value

        Returns:
            List of event dicts (details parsed from JSON) ordered oldest → newest
        """
        raise NotImplementedError

    def _match_steps(
        self,
        steps: list[StepSpec],
        history: list[dict[str, Any]],
        within_n_events: int | None,
        within_seconds: int | None,
        order_matters: bool,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Walk history and try to match all steps.

        Returns:
            (matched: bool, evidence_steps: list of matched event dicts)
        """
        raise NotImplementedError

    @staticmethod
    def _event_matches_step(event: dict[str, Any], step: StepSpec) -> bool:
        """Return True if event satisfies the step's event_type glob and conditions."""
        raise NotImplementedError

    @staticmethod
    def _within_time_window(
        first: datetime, last: datetime, within_seconds: int
    ) -> bool:
        """Return True if last - first <= within_seconds."""
        raise NotImplementedError
