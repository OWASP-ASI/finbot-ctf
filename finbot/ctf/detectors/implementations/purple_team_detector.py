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
# Fraction of the expected directive's content words that must appear in the
# submission for a fuzzy directive match.
DEFAULT_DIRECTIVE_THRESHOLD = 0.6
SUBMISSION_EVENT_TYPE = "business.investigation.submitted"

# Short function words that carry no forensic meaning. Dropped before the
# directive token-overlap comparison so word order and filler do not matter.
_STOPWORDS = frozenset(
    {
        "the", "a", "an", "to", "and", "or", "of", "in", "on", "for", "with",
        "it", "its", "that", "this", "was", "were", "is", "are", "be", "by",
        "as", "at", "from", "into", "then", "so", "all", "any",
    }
)


def _normalize(value: Any) -> str:
    """Lowercase, strip, and collapse internal whitespace for comparison."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _content_tokens(text: str) -> list[str]:
    """Significant words from a normalized string: len >= 3 and not a stopword."""
    return [
        w for w in re.findall(r"[a-z0-9]+", text) if len(w) >= 3 and w not in _STOPWORDS
    ]


def _token_covered(expected_word: str, submission_tokens: set[str]) -> bool:
    """A word is covered by an exact match or a shared prefix (light stemming).

    The prefix rule lets 'email' match 'emailed' and 'transfer' match
    'transfers' without a full stemming dependency.
    """
    for s in submission_tokens:
        if s == expected_word:
            return True
        if len(expected_word) >= 4 and len(s) >= 4 and (
            s.startswith(expected_word) or expected_word.startswith(s)
        ):
            return True
    return False


@register_detector("PurpleTeamDetector")
class PurpleTeamDetector(BaseDetector):
    """Scores a forensic investigation submission with partial credit.

    Each field (server, tool, directive) scores independently. The server and
    tool fields use exact normalized matching. The directive is free text, so
    by default it uses token overlap: the submission counts as correct when a
    configurable fraction of the expected directive's content words appear in
    the answer, order-independent and with light prefix stemming. This lets the
    student paraphrase. Set directive_match: exact to require a full match.

    Configuration:
        expected: dict            -- the known answer, any of {server, tool, directive}
        field_points: dict        -- points per field (default 33/33/34)
        min_score: int            -- score needed to complete the challenge (default 50)
        directive_match: str      -- "fuzzy" (default) or "exact"
        directive_threshold: float -- fuzzy overlap fraction needed (default 0.6)

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

        threshold = self.config.get("directive_threshold", DEFAULT_DIRECTIVE_THRESHOLD)
        if not isinstance(threshold, (int, float)) or not 0 < threshold <= 1:
            raise ValueError("directive_threshold must be a number in (0, 1]")

    def get_relevant_event_types(self) -> list[str]:
        return [SUBMISSION_EVENT_TYPE]

    def _field_correct(self, field: str, submitted: Any, expected: Any) -> bool:
        """Score a single field.

        Server and tool use exact normalized matching. The free-text directive
        uses token overlap by default so the student can paraphrase: it counts
        as correct when a configurable fraction of the expected content words
        appear in the submission (order-independent, light prefix stemming). A
        verbatim substring also counts. Set directive_match: exact to require a
        full normalized match.
        """
        sub_norm = _normalize(submitted)
        exp_norm = _normalize(expected)
        if not exp_norm or not sub_norm:
            return False

        if field != "directive" or self.config.get("directive_match", "fuzzy") == "exact":
            return sub_norm == exp_norm

        # Fuzzy directive: verbatim substring is an easy accept.
        if exp_norm in sub_norm or sub_norm in exp_norm:
            return True

        expected_tokens = _content_tokens(exp_norm)
        if not expected_tokens:
            return sub_norm == exp_norm

        submission_tokens = set(_content_tokens(sub_norm))
        covered = sum(
            1 for w in expected_tokens if _token_covered(w, submission_tokens)
        )
        threshold = float(
            self.config.get("directive_threshold", DEFAULT_DIRECTIVE_THRESHOLD)
        )
        return covered / len(expected_tokens) >= threshold

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
