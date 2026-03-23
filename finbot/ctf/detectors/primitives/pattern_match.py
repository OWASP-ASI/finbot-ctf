"""Pattern Match Detector

Generic regex/keyword matching on event fields.
The foundational primitive for text-based detection.
All pattern-matching helpers live here (no separate utils module).
"""

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


def _matches_pattern(
    text: str,
    pattern: str,
    case_sensitive: bool = False,
    is_regex: bool = False,
) -> tuple[bool, str | None]:
    """Check if text matches a pattern. Returns (matched, matched_text)."""
    if not text or not pattern:
        return False, None

    if is_regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            match = re.search(pattern, text, flags)
            if match:
                return True, match.group(0)
            return False, None
        except re.error:
            pass
            
    search_text = text if case_sensitive else text.lower()
    search_pattern = pattern if case_sensitive else pattern.lower()
    if search_pattern in search_text:
        start = search_text.find(search_pattern)
        matched = text[start : start + len(pattern)]
        return True, matched
    return False, None


def _extract_context(
    text: str, match_start: int, match_length: int, context_chars: int = 50
) -> str:
    """Extract context around a match for evidence."""
    start = max(0, match_start - context_chars)
    end = min(len(text), match_start + match_length + context_chars)
    context = text[start:end]
    if start > 0:
        context = "..." + context
    if end < len(text):
        context = context + "..."
    return context


def _parse_pattern(pattern_config: str | dict) -> tuple[str, bool]:
    """Parse pattern config into (pattern, is_regex) tuple."""
    if isinstance(pattern_config, dict):
        if "regex" in pattern_config:
            return pattern_config["regex"], True
        return str(list(pattern_config.values())[0]), False
    return str(pattern_config), False


def run_pattern_match(
    text: str,
    patterns: list[str | dict],
    case_sensitive: bool = False,
) -> list[dict[str, Any]]:
    """Run pattern matching against text. Shared logic for pattern-based detectors.

    Args:
        text: Text to search in.
        patterns: List of patterns (strings for literal, or dict with 'regex' key).
        case_sensitive: Whether matching is case-sensitive.

    Returns:
        List of match dicts with keys: pattern, matched, context, is_regex.
    """
    if not text:
        return []

    matches = []
    for pattern_config in patterns:
        pattern, is_regex = _parse_pattern(pattern_config)
        matched, matched_text = _matches_pattern(
            text, pattern, case_sensitive, is_regex
        )
        if matched and matched_text:
            match_start = (
                text.find(matched_text)
                if case_sensitive
                else text.lower().find(matched_text.lower())
            )
            context = _extract_context(text, match_start, len(matched_text))
            matches.append(
                {
                    "pattern": pattern,
                    "matched": matched_text,
                    "context": context,
                    "is_regex": is_regex,
                }
            )
    return matches


@register_detector("PatternMatchDetector")
class PatternMatchDetector(BaseDetector):
    """Matches patterns (keywords or regex) against event field values.

    Configuration:
        field: str - Event field to check (required)
        patterns: list - Patterns to match (required)
            Each pattern can be:
            - A string (literal match)
            - A dict with 'regex' key for regex patterns
        match_mode: str - "any" (default) or "all"
        case_sensitive: bool - Default False
        min_matches: int - Minimum matches required (default 1)

    Example YAML:
        detector_class: PatternMatchDetector
        detector_config:
          field: "response_content"
          patterns:
            - "system prompt"
            - "you are a"
            - regex: "(?i)instructions?:"
          match_mode: "any"
    """

    def _validate_config(self) -> None:
        if "field" not in self.config:
            raise ValueError("PatternMatchDetector requires 'field' config")
        if "patterns" not in self.config:
            raise ValueError("PatternMatchDetector requires 'patterns' config")
        if not isinstance(self.config["patterns"], list):
            raise ValueError("'patterns' must be a list")
        if not self.config["patterns"]:
            raise ValueError("'patterns' cannot be empty")

        match_mode = self.config.get("match_mode", "any")
        if match_mode not in ("any", "all"):
            raise ValueError("match_mode must be 'any' or 'all'")

    def get_relevant_event_types(self) -> list[str]:
        """Override in subclass or configure via YAML.

        Default: match all LLM response events.
        """
        return self.config.get("event_types", ["agent.*.llm_request_success"])

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if event field matches configured patterns.
        Only needs the current event, db is unused.
        """
        field = self.config["field"]
        patterns = self.config["patterns"]
        match_mode = self.config.get("match_mode", "any")
        case_sensitive = self.config.get("case_sensitive", False)
        min_matches = self.config.get("min_matches", 1)

        field_value = event.get(field)
        if field_value is None:
            return DetectionResult(
                detected=False,
                message=f"Field '{field}' not found in event",
            )

        if not isinstance(field_value, str):
            field_value = str(field_value)

        matches = run_pattern_match(field_value, patterns, case_sensitive)

        if match_mode == "all":
            detected = len(matches) == len(patterns)
        else:
            detected = len(matches) >= min_matches

        if not detected:
            return DetectionResult(
                detected=False,
                confidence=len(matches) / len(patterns) if patterns else 0,
                message=f"Matched {len(matches)}/{len(patterns)} patterns (need {min_matches})",
                evidence={"matches": matches} if matches else {},
            )

        return DetectionResult(
            detected=True,
            confidence=min(1.0, len(matches) / len(patterns) + 0.2),
            message=f"Pattern match: {len(matches)} pattern(s) matched in '{field}'",
            evidence={
                "field": field,
                "matches": matches,
                "total_patterns": len(patterns),
            },
        )
