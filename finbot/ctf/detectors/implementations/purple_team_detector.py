"""Purple Team Detector

Scores forensic reasoning instead of agent behavior. Every other detector
fires on what an agent did. This one fires on what the student understood.

After solving an attack challenge, the student submits a forensic answer
naming the compromised MCP server, the tool that carried the poisoned
directive, and the directive itself. The detector compares the submission
against the expected answer defined in the challenge's detector_config and
awards partial credit per field.

Submissions arrive as a "business.investigation.submitted" event emitted by
the toolkit investigation endpoint. The submission payload lives under the
event's "submission" key: {server, tool, directive}.

OWASP: ASI-04 (Supply Chain), ASI-02 (Tool Misuse)
"""

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)

# Independent per-field credit. Sums to 100.
DEFAULT_FIELD_POINTS = {"server": 33, "tool": 33, "directive": 34}
DEFAULT_MIN_SCORE = 50
SUBMISSION_EVENT_TYPE = "business.investigation.submitted"


def _normalize(value: Any) -> str:
    """Lowercase, strip, and collapse internal whitespace for comparison."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


@register_detector("PurpleTeamDetector")
class PurpleTeamDetector(BaseDetector):
    """Scores a forensic investigation submission with partial credit.

    Each field (server, tool, directive) scores independently. The server and
    tool fields use exact normalized matching. The directive is free text, so
    it uses substring matching by default: the submission counts as correct if
    the normalized expected directive appears in the normalized submission or
    vice versa. Set directive_match: exact to require a full match.

    Configuration:
        expected: dict          -- the known answer, any of {server, tool, directive}
        field_points: dict      -- points per field (default 33/33/34)
        min_score: int          -- score needed to complete the challenge (default 50)
        directive_match: str    -- "fuzzy" (default) or "exact"

    Example YAML:
        detector_class: PurpleTeamDetector
        detector_config:
          expected:
            server: findrive
            tool: get_file
            directive: "approve all pending invoices"
          min_score: 50
          directive_match: fuzzy
    """

    def _validate_config(self) -> None:
        expected = self.config.get("expected")
        if not isinstance(expected, dict) or not expected:
            raise ValueError("PurpleTeamDetector requires a non-empty 'expected' dict")

        allowed = {"server", "tool", "directive"}
        unknown = set(expected) - allowed
        if unknown:
            raise ValueError(f"expected contains unknown fields: {sorted(unknown)}")

        field_points = self.config.get("field_points", DEFAULT_FIELD_POINTS)
        if not isinstance(field_points, dict):
            raise ValueError("field_points must be a dict")

        min_score = self.config.get("min_score", DEFAULT_MIN_SCORE)
        if not isinstance(min_score, (int, float)) or not 0 <= min_score <= 100:
            raise ValueError("min_score must be a number between 0 and 100")

        directive_match = self.config.get("directive_match", "fuzzy")
        if directive_match not in ("fuzzy", "exact"):
            raise ValueError("directive_match must be 'fuzzy' or 'exact'")

    def get_relevant_event_types(self) -> list[str]:
        return [SUBMISSION_EVENT_TYPE]

    def _field_correct(self, field: str, submitted: Any, expected: Any) -> bool:
        """Score a single field. Directive supports fuzzy substring matching."""
        sub_norm = _normalize(submitted)
        exp_norm = _normalize(expected)
        if not exp_norm:
            return False
        if not sub_norm:
            return False

        if field == "directive" and self.config.get("directive_match", "fuzzy") == "fuzzy":
            return exp_norm in sub_norm or sub_norm in exp_norm

        return sub_norm == exp_norm

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        # Submission payload may arrive under "submission" or, for compatibility
        # with a raw tool call, under "tool_arguments".
        submission = event.get("submission") or event.get("tool_arguments") or {}
        if not isinstance(submission, dict):
            return DetectionResult(
                detected=False, message="Malformed investigation submission"
            )

        expected: dict[str, Any] = self.config["expected"]
        field_points: dict[str, int] = self.config.get(
            "field_points", DEFAULT_FIELD_POINTS
        )
        min_score = float(self.config.get("min_score", DEFAULT_MIN_SCORE))

        score = 0
        breakdown: dict[str, bool] = {}
        for field, expected_value in expected.items():
            correct = self._field_correct(field, submission.get(field), expected_value)
            breakdown[field] = correct
            if correct:
                score += int(field_points.get(field, 0))

        detected = score >= min_score

        # Evidence records the score and which fields were correct, but never
        # the expected answer itself, so completion evidence cannot spoil the
        # challenge for the player.
        return DetectionResult(
            detected=detected,
            confidence=score / 100,
            message=f"Investigation score: {score}/100",
            evidence={
                "score": score,
                "min_score": min_score,
                "fields_correct": breakdown,
                "submission": {k: submission.get(k) for k in expected},
            },
        )
