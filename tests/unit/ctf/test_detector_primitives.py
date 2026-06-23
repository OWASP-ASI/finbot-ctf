"""
CTF Detector Primitive Tests

User Story: As a platform engineer, I want unit tests for detector primitives
            so that the building blocks used by all detectors are verified
            in isolation.

Acceptance Criteria:
- PatternMatchDetector + helper functions (PRM-PAT-001 through 027)
- ToolCallDetector + _check_condition operators (PRM-TOL-001 through 017)
- PIIDetector + scan_pii function (PRM-PII-001 through 011)

Production Impact
=================
PatternMatchDetector, ToolCallDetector, and PIIDetector are the building
blocks for every production detector. A bug in any primitive propagates
silently to every detector that inherits from it.

- Pattern bugs    Case/regex errors let attackers bypass detection by varying
                  casing or exploiting the regex fallback path.
- Config failures A misconfigured primitive that starts silently (no "field",
                  no "tool_name", empty patterns) provides zero protection
                  while appearing healthy in monitoring.
- Crash-and-silence  An unhandled exception on a malformed event kills the
                  detector coroutine; all subsequent events in the pipeline
                  queue are never checked until the service restarts.
- PII gaps        Missed SSN/EIN patterns let customer financial data leak
                  through agent responses without a security alert.
"""

import pytest
from unittest.mock import MagicMock

from finbot.ctf.detectors.primitives.pattern_match import (
    PatternMatchDetector,
    _matches_pattern,
    _extract_context,
    _parse_pattern,
    run_pattern_match,
)
from finbot.ctf.detectors.primitives.tool_call import ToolCallDetector
from finbot.ctf.detectors.primitives.pii import PIIDetector, scan_pii
from finbot.ctf.detectors.primitives.pi_jb import PromptInjectionDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
    return MagicMock()


# ===========================================================================
# _matches_pattern
# ===========================================================================

class TestMatchesPattern:

    @pytest.mark.unit
    def test_prm_pat_001_empty_text_returns_false(self):
        """PRM-PAT-001: Empty text never matches any pattern

        Title: Empty string input returns (False, None)
        Description: When the input text is empty there is nothing to search.
                     The function must return False without raising an exception.

        Steps:
        1. Call _matches_pattern with text="" and pattern="test"

        Expected Results:
        1. matched is False
        2. matched_text is None

        Impact: If an exception is raised on empty text, any event with a
                missing or empty field crashes the detector, silencing all
                subsequent events in the pipeline. Every downstream detector
                built on this primitive inherits the crash-and-silence failure.
        """
        matched, text = _matches_pattern("", "test")
        assert not matched
        assert text is None

    @pytest.mark.unit
    def test_prm_pat_002_empty_pattern_returns_false(self):
        """PRM-PAT-002: Empty pattern never matches any text

        Title: Empty pattern string returns (False, None)
        Description: An empty pattern is meaningless. The function must return
                     False without raising an exception.

        Steps:
        1. Call _matches_pattern with a non-empty text and pattern=""

        Expected Results:
        1. matched is False

        Impact: Same crash-and-silence risk as PRM-PAT-001; a blank pattern
                config key would crash every event processed by that detector.
                Because all production detectors share this primitive, a single
                misconfigured pattern key takes down detection across the board.
        """
        matched, _ = _matches_pattern("hello world", "")
        assert not matched

    @pytest.mark.unit
    def test_prm_pat_003_case_insensitive_literal(self):
        """PRM-PAT-003: Default case-insensitive literal matching works

        Title: Lowercase pattern matches uppercase text by default
        Description: When case_sensitive=False (default), the function must
                     find the pattern regardless of case and return the
                     original casing of the matched text.

        Steps:
        1. Call _matches_pattern with text="Hello World" and pattern="hello"
           using default case_sensitive=False

        Expected Results:
        1. matched is True
        2. matched_text is "Hello" (preserving original casing)

        Impact: If case folding is broken, attackers bypass detection by
                changing the casing of a bypass keyword (e.g. "IGNORE POLICY"
                instead of "ignore policy"). Every challenge that relies on
                case-insensitive keyword detection is silently defeated.
        """
        matched, text = _matches_pattern("Hello World", "hello")
        assert matched
        assert text == "Hello"

    @pytest.mark.unit
    def test_prm_pat_004_case_sensitive_no_match(self):
        """PRM-PAT-004: Case-sensitive match fails on wrong case

        Title: Lowercase pattern does not match uppercase text in strict mode
        Description: When case_sensitive=True, casing must match exactly.
                     A lowercase pattern must not match an uppercase string.

        Steps:
        1. Call _matches_pattern with text="Hello World", pattern="hello",
           case_sensitive=True

        Expected Results:
        1. matched is False

        Impact: If the function returns True when it should return False, every
                event triggers a false positive regardless of content, causing
                alert fatigue. Operators disable the detector to stop the noise,
                and the challenge provides zero protection from that point on.
        """
        matched, _ = _matches_pattern("Hello World", "hello", case_sensitive=True)
        assert not matched

    @pytest.mark.unit
    def test_prm_pat_005_case_sensitive_match(self):
        """PRM-PAT-005: Case-sensitive match succeeds on correct case

        Title: Exact-case pattern matches text in strict mode
        Description: When case_sensitive=True and the pattern case exactly
                     matches the text, the function must return True with
                     the matched text.

        Steps:
        1. Call _matches_pattern with text="Hello World", pattern="Hello",
           case_sensitive=True

        Expected Results:
        1. matched is True
        2. matched_text is "Hello"

        Impact: If strict-mode matching silently ignores case_sensitive=True,
                a challenge configured for exact-case matching provides no
                protection; any casing variation evades it. The security test
                passes during development but fails in production against a
                real adversary.
        """
        matched, text = _matches_pattern("Hello World", "Hello", case_sensitive=True)
        assert matched
        assert text == "Hello"

    @pytest.mark.unit
    def test_prm_pat_006_regex_match(self):
        """PRM-PAT-006: Regex pattern matches and returns the captured group

        Title: is_regex=True activates regex search mode
        Description: When is_regex=True, the pattern is compiled as a regular
                     expression and re.search is used. The matched group is
                     returned as matched_text.

        Steps:
        1. Call _matches_pattern with text="invoice #12345",
           pattern=r"\\d{5}", is_regex=True

        Expected Results:
        1. matched is True
        2. matched_text is "12345"

        Impact: If regex mode returns the wrong match group (or no match), the
                detection result carries wrong evidence — the security team
                cannot reconstruct which part of the text triggered the alert.
                Incident response is delayed while analysts hunt for evidence
                that was never captured correctly.
        """
        matched, text = _matches_pattern("invoice #12345", r"\d{5}", is_regex=True)
        assert matched
        assert text == "12345"

    @pytest.mark.unit
    def test_prm_pat_007_invalid_regex_falls_back_to_literal(self):
        """PRM-PAT-007: Invalid regex silently falls back to literal match

        Title: re.error on invalid pattern is caught and not propagated
        Description: When is_regex=True but the pattern is not valid regex,
                     the function must catch re.error and continue. If the
                     pattern also does not appear as a literal, the result
                     is (False, None).

        Steps:
        1. Call _matches_pattern with text="no match here",
           pattern="[invalid", is_regex=True

        Expected Results:
        1. matched is False
        2. No re.error exception is raised

        Impact: If an invalid regex raises instead of falling back, a single
                typo in any challenge YAML detector_config crashes the detector
                permanently for the lifetime of the process. All subsequent
                events queue up unprocessed until the service is restarted.
        """
        matched, _ = _matches_pattern("no match here", "[invalid", is_regex=True)
        assert not matched

    @pytest.mark.unit
    def test_prm_pat_028_valid_regex_non_match_no_literal_fallback(self):
        """PRM-PAT-028: Valid regex that does not match returns (False, None) — no literal fallback

        Title: _matches_pattern with valid regex and no match returns (False, None) without literal fallback
        Basically question: Does a valid regex that does not match the text prevent a false
                            positive from the literal fallback?
        Description: When is_regex=True and the pattern is a valid regex but the regex
                     does not match the text, the function falls through to a literal
                     substring search using the raw regex string. If the text happens to
                     contain the literal characters of the regex pattern (e.g. the text
                     itself is a regex string), a false positive is returned.

        Steps:
        1. Build text that contains the literal characters of the regex pattern but
           does NOT satisfy the regex semantically:
           text = "invoice\\d+"  (literal backslash-d-plus, no actual digits)
           pattern = r"\d+" (matches one or more decimal digits)
        2. Call _matches_pattern with is_regex=True

        Expected Results:
        1. matched is False  — the regex found no digits, so no match
        2. matched_text is None

        Impact: The regex fallthrough produces a false positive whenever the raw
                pattern string appears as a substring in the text. A challenge
                YAML that uses a regex like r"invoice\\d+" could spuriously fire on
                events whose content contains the literal regex string rather than
                an actual invoice number, generating false alerts and misleading
                analysts into investigating non-attacks.
        """
        # text contains the literal characters r"\d+" but no actual decimal digits
        # regex r"\d+" must not match — the fallback to literal must not fire
        matched, text = _matches_pattern("invoice\\d+", r"\d+", is_regex=True)
        assert not matched, (
            "Valid regex non-match fell through to literal substring search "
            "and returned True when the pattern string appeared literally in the text"
        )
        assert text is None


# ===========================================================================
# _extract_context
# ===========================================================================

class TestExtractContext:

    @pytest.mark.unit
    def test_prm_pat_008_context_in_middle(self):
        """PRM-PAT-008: Context extracted around a mid-string match includes ellipses

        Title: Leading and trailing ellipses added when match is not at boundary
        Description: When the match is far from both start and end, the context
                     window should be surrounded by "..." on both sides to
                     indicate truncation.

        Steps:
        1. Build a 125-character string with "MATCH" at position 60
        2. Call _extract_context with match_start=60, match_length=5

        Expected Results:
        1. "MATCH" is present in the returned context
        2. Context starts with "..."
        3. Context ends with "..."

        Impact: If ellipsis markers are missing, analysts reviewing the evidence
                cannot tell whether the matched text is surrounded by additional
                relevant content, making triage decisions less reliable. A
                missing leading ellipsis could lead analysts to conclude the
                match appeared at the start of a message when it did not.
        """
        ctx = _extract_context("a" * 60 + "MATCH" + "b" * 60, 60, 5)
        assert "MATCH" in ctx
        assert ctx.startswith("...")
        assert ctx.endswith("...")

    @pytest.mark.unit
    def test_prm_pat_009_context_at_start(self):
        """PRM-PAT-009: No leading ellipsis when match is at the beginning

        Title: Context at position 0 has no leading "..."
        Description: When the match starts at the beginning of the text there
                     are no preceding characters to truncate so no leading
                     ellipsis should be added.

        Steps:
        1. Call _extract_context with text="MATCH at start",
           match_start=0, match_length=5

        Expected Results:
        1. Returned context does not start with "..."

        Impact: If a spurious leading "..." is added, analysts waste time
                looking for truncated preceding text that does not exist.
                Evidence formatting becomes untrustworthy, eroding confidence
                in the security dashboard and slowing incident response.
        """
        ctx = _extract_context("MATCH at start", 0, 5)
        assert not ctx.startswith("...")

    @pytest.mark.unit
    def test_prm_pat_010_context_at_end(self):
        """PRM-PAT-010: No trailing ellipsis when match is at the end

        Title: Context at the end of text has no trailing "..."
        Description: When the match ends at the last character there are no
                     following characters to truncate so no trailing ellipsis
                     should be added.

        Steps:
        1. Build text="text ends with MATCH"
        2. Call _extract_context with match_start at the last 5 characters

        Expected Results:
        1. Returned context does not end with "..."

        Impact: Same issue as PRM-PAT-009 but for trailing context. A spurious
                trailing ellipsis misleads analysts into believing additional
                text was truncated, potentially causing them to request full
                logs when the evidence is already complete.
        """
        text = "text ends with MATCH"
        ctx = _extract_context(text, len(text) - 5, 5)
        assert not ctx.endswith("...")


# ===========================================================================
# _parse_pattern
# ===========================================================================

class TestParsePattern:

    @pytest.mark.unit
    def test_prm_pat_011_string_pattern_is_literal(self):
        """PRM-PAT-011: String input is treated as a literal pattern

        Title: Plain string config returns (pattern, is_regex=False)
        Description: When the pattern config is a plain string it is a
                     literal keyword search, not a regex.

        Steps:
        1. Call _parse_pattern with "hello"

        Expected Results:
        1. Returned pattern is "hello"
        2. is_regex is False

        Impact: If a plain string is incorrectly treated as regex, keywords
                containing regex metacharacters (e.g. "$50,000") cause a
                re.error crash, silencing the detector for all subsequent
                events until the service restarts.
        """
        pattern, is_regex = _parse_pattern("hello")
        assert pattern == "hello"
        assert not is_regex

    @pytest.mark.unit
    def test_prm_pat_012_dict_with_regex_key(self):
        """PRM-PAT-012: Dict with 'regex' key is treated as a regex pattern

        Title: {"regex": "..."} config returns (pattern, is_regex=True)
        Description: YAML challenge configs use {"regex": "..."} to declare
                     regex patterns. _parse_pattern must detect this form.

        Steps:
        1. Call _parse_pattern with {"regex": r"\\d+"}

        Expected Results:
        1. Returned pattern equals r"\\d+"
        2. is_regex is True

        Impact: If {"regex": "..."} is not recognized as a regex pattern, all
                regex-configured detectors fall back to literal search, missing
                attacks that only match the regex (e.g. amount ranges like
                \\d{5,}). The challenge appears to work but never detects the
                intended attack pattern.
        """
        pattern, is_regex = _parse_pattern({"regex": r"\d+"})
        assert pattern == r"\d+"
        assert is_regex

    @pytest.mark.unit
    def test_prm_pat_013_dict_without_regex_key(self):
        """PRM-PAT-013: Dict without 'regex' key is treated as a literal

        Title: {"literal": "test"} config returns (pattern, is_regex=False)
        Description: A dict without a "regex" key is treated as a literal
                     pattern using the first value in the dict.

        Steps:
        1. Call _parse_pattern with {"literal": "test"}

        Expected Results:
        1. Returned pattern is "test"
        2. is_regex is False

        Impact: If a non-regex dict is incorrectly treated as regex, a literal
                keyword containing regex metacharacters causes a crash and the
                detector goes silent. All events after the crash are unprocessed
                until an operator restarts the service.
        """
        pattern, is_regex = _parse_pattern({"literal": "test"})
        assert pattern == "test"
        assert not is_regex


# ===========================================================================
# run_pattern_match
# ===========================================================================

class TestRunPatternMatch:

    @pytest.mark.unit
    def test_prm_pat_014_empty_text_returns_no_matches(self):
        """PRM-PAT-014: Empty text input returns an empty match list

        Title: No patterns can match against an empty string
        Description: When the input text is empty the function must return
                     an empty list without raising an exception.

        Steps:
        1. Call run_pattern_match with text="" and patterns=["hello"]

        Expected Results:
        1. Returns an empty list []

        Impact: Same crash risk as PRM-PAT-001 but at the higher-level function
                that all PatternMatchDetector instances call. A crash here takes
                down every PatternMatchDetector-based challenge simultaneously,
                providing zero pattern-based protection across the platform.
        """
        assert run_pattern_match("", ["hello"]) == []

    @pytest.mark.unit
    def test_prm_pat_015_multiple_patterns_returns_all_matches(self):
        """PRM-PAT-015: Multiple matching patterns are all returned

        Title: Each matching pattern produces one entry in the result list
        Description: When multiple patterns all match the input text, the
                     function must return one match dict per pattern.

        Steps:
        1. Call run_pattern_match with text="hello world foo"
           and patterns=["hello", "foo"]

        Expected Results:
        1. Returns a list with 2 entries
        2. Both "hello" and "foo" appear in the matched patterns

        Impact: If only the first matching pattern is returned, the evidence
                dict is incomplete — analysts see only partial proof of the
                attack, and the confidence score underestimates severity. An
                attack using multiple bypass keywords appears less suspicious
                than it actually is.
        """
        matches = run_pattern_match("hello world foo", ["hello", "foo"])
        assert len(matches) == 2
        patterns_matched = {m["pattern"] for m in matches}
        assert "hello" in patterns_matched
        assert "foo" in patterns_matched

    @pytest.mark.unit
    def test_prm_pat_016_no_match_returns_empty(self):
        """PRM-PAT-016: No matching patterns returns an empty list

        Title: Patterns that do not appear in the text produce no results
        Description: When none of the configured patterns appear in the text
                     the function must return an empty list.

        Steps:
        1. Call run_pattern_match with text="nothing here"
           and patterns=["xyz", "abc"]

        Expected Results:
        1. Returns an empty list []

        Impact: If a non-matching scan returns a non-empty list (false positive),
                every event triggers detection regardless of content, making the
                detector useless. Alert fatigue sets in and operators disable the
                detector, eliminating protection for the challenge entirely.
        """
        assert run_pattern_match("nothing here", ["xyz", "abc"]) == []

    @pytest.mark.unit
    def test_prm_pat_017_regex_pattern_in_list(self):
        """PRM-PAT-017: Regex dict patterns work inside run_pattern_match

        Title: {"regex": "..."} entries are compiled and matched correctly
        Description: run_pattern_match accepts mixed pattern lists containing
                     both plain strings and regex dicts. Regex patterns must
                     be activated via _parse_pattern.

        Steps:
        1. Call run_pattern_match with text="invoice 12345"
           and patterns=[{"regex": r"\\d{5}"}]

        Expected Results:
        1. Returns a list with 1 entry
        2. That entry has is_regex=True

        Impact: If regex dicts are not processed by _parse_pattern, the raw
                dict string is treated as a literal keyword and no events ever
                match — the regex challenge is permanently disabled without any
                error message or monitoring signal.
        """
        matches = run_pattern_match("invoice 12345", [{"regex": r"\d{5}"}])
        assert len(matches) == 1
        assert matches[0]["is_regex"] is True


# ===========================================================================
# PatternMatchDetector
# ===========================================================================

class TestPatternMatchDetector:

    def _make(self, config):
        return PatternMatchDetector(challenge_id="c", config=config)

    @pytest.mark.unit
    def test_prm_pat_018_config_missing_field_raises(self):
        """PRM-PAT-018: Missing 'field' config key raises ValueError at init

        Title: 'field' is a required configuration key
        Description: PatternMatchDetector cannot operate without knowing which
                     event field to search. Omitting 'field' must fail early.

        Steps:
        1. Attempt to create PatternMatchDetector with patterns but no field

        Expected Results:
        1. ValueError is raised during __init__
        2. Error message contains "field"

        Impact: If a misconfigured detector (no field) starts silently, it
                crashes on the first event with a KeyError, silencing all
                subsequent events in the pipeline — a "silent startup, loud
                crash" failure that is difficult to diagnose in production.
        """
        with pytest.raises(ValueError, match="field"):
            self._make({"patterns": ["test"]})

    @pytest.mark.unit
    def test_prm_pat_019_config_missing_patterns_raises(self):
        """PRM-PAT-019: Missing 'patterns' config key raises ValueError at init

        Title: 'patterns' is a required configuration key
        Description: PatternMatchDetector cannot operate without a list of
                     patterns to match. Omitting 'patterns' must fail early.

        Steps:
        1. Attempt to create PatternMatchDetector with field but no patterns

        Expected Results:
        1. ValueError is raised during __init__
        2. Error message contains "patterns"

        Impact: Same as PRM-PAT-018 but for the patterns key. A detector with
                no patterns configured would never match anything anyway, so
                failing fast is strictly better than running silently and giving
                operators false confidence that the challenge is protected.
        """
        with pytest.raises(ValueError, match="patterns"):
            self._make({"field": "content"})

    @pytest.mark.unit
    def test_prm_pat_020_empty_patterns_raises(self):
        """PRM-PAT-020: Empty patterns list raises ValueError at init

        Title: Patterns list must not be empty
        Description: An empty patterns list means nothing would ever be
                     detected. This is a configuration error that must be
                     caught at initialization.

        Steps:
        1. Attempt to create PatternMatchDetector with patterns=[]

        Expected Results:
        1. ValueError is raised during __init__
        2. Error message contains "empty"

        Impact: If an empty list is accepted, the detector runs without error
                but can never detect anything — operators see a "healthy"
                detector in monitoring that provides zero protection. The gap
                goes unnoticed until a real attack is reviewed post-incident.
        """
        with pytest.raises(ValueError, match="empty"):
            self._make({"field": "content", "patterns": []})

    @pytest.mark.unit
    def test_prm_pat_021_invalid_match_mode_raises(self):
        """PRM-PAT-021: Invalid match_mode value raises ValueError at init

        Title: match_mode must be 'any' or 'all'
        Description: Any value other than "any" or "all" for match_mode is
                     a configuration error and must be caught at init.

        Steps:
        1. Attempt to create PatternMatchDetector with match_mode="none"

        Expected Results:
        1. ValueError is raised during __init__
        2. Error message contains "match_mode"

        Impact: If match_mode="none" is silently accepted and treated as "any",
                the challenge behaves contrary to its YAML config without any
                error, making the challenge definition misleading and the
                security test result invalid.
        """
        with pytest.raises(ValueError, match="match_mode"):
            self._make({"field": "content", "patterns": ["x"], "match_mode": "none"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pat_022_field_missing_from_event(self):
        """PRM-PAT-022: Missing configured field in event returns not detected

        Title: Absence of the target field in the event skips detection
        Description: When the event does not contain the configured field
                     name there is nothing to search and detection must
                     return False.

        Steps:
        1. Create detector with field="response" and patterns=["secret"]
        2. Call check_event with an event that does not have "response"

        Expected Results:
        1. check_event returns detected=False
        2. Return message references the missing field name

        Impact: If an exception is raised instead of returning detected=False,
                a single event missing a field crashes the detector coroutine,
                silencing all subsequent real attacks. Any adversary that sends
                a malformed event before a real attack can disable detection.
        """
        detector = self._make({"field": "response", "patterns": ["secret"]})
        result = await detector.check_event({"other_field": "value"}, _mock_db())
        assert not result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pat_023_non_string_field_coerced(self):
        """PRM-PAT-023: Non-string field value is coerced to string before matching

        Title: Integer and other non-string field values are searchable
        Description: Event field values may be integers or other types. The
                     detector must convert them to string before running
                     pattern matching.

        Steps:
        1. Create detector with field="count" and patterns=["42"]
        2. Call check_event with event {"count": 42} (integer value)

        Expected Results:
        1. check_event returns detected=True
        2. Pattern "42" is found in the string representation of 42

        Impact: If integer/numeric field values are not coerced to string, a
                numeric amount field can never be searched by pattern, defeating
                any detector that looks for specific numbers in event data. An
                attacker submitting a numeric amount rather than a string bypasses
                detection entirely.
        """
        detector = self._make({"field": "count", "patterns": ["42"]})
        result = await detector.check_event({"count": 42}, _mock_db())
        assert result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pat_024_any_mode_one_match_sufficient(self):
        """PRM-PAT-024: match_mode='any' triggers detection on the first matching pattern

        Title: A single matching pattern is sufficient in 'any' mode
        Description: When match_mode is "any" (the default), detection must
                     succeed as soon as at least one pattern matches,
                     regardless of how many patterns are configured.

        Steps:
        1. Create detector with match_mode="any" and patterns=["hello", "xyz"]
        2. Call check_event with text that contains "hello" but not "xyz"

        Expected Results:
        1. check_event returns detected=True
        2. Only the matching pattern appears in evidence

        Impact: If "any" mode requires all patterns, a detector configured to
                fire on any suspicious keyword only fires when all keywords
                appear together — sophisticated attackers using a single bypass
                phrase evade detection. Challenges relying on keyword lists
                provide zero protection.
        """
        detector = self._make(
            {"field": "text", "patterns": ["hello", "xyz"], "match_mode": "any"}
        )
        result = await detector.check_event({"text": "hello world"}, _mock_db())
        assert result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pat_025_all_mode_requires_all_matches(self):
        """PRM-PAT-025: match_mode='all' requires every pattern to match

        Title: A partial match in 'all' mode does not trigger detection
        Description: When match_mode is "all", every configured pattern must
                     appear in the text. If any pattern is missing, detection
                     must return False.

        Steps:
        1. Create detector with match_mode="all" and patterns=["hello", "world"]
        2. Call check_event with text="hello there" (missing "world")

        Expected Results:
        1. check_event returns detected=False
        2. confidence reflects the partial match ratio

        Impact: If "all" mode fires on a partial match, false positives flood
                the alert queue — legitimate events trigger security alerts,
                leading to alert fatigue and operator disengagement. Real attacks
                are buried in noise and missed during review.
        """
        detector = self._make(
            {"field": "text", "patterns": ["hello", "world"], "match_mode": "all"}
        )
        result = await detector.check_event({"text": "hello there"}, _mock_db())
        assert not result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pat_026_all_mode_all_match(self):
        """PRM-PAT-026: match_mode='all' triggers detection when every pattern matches

        Title: All patterns present in 'all' mode triggers detection
        Description: When every configured pattern appears in the text and
                     match_mode is "all", detection must return True.

        Steps:
        1. Create detector with match_mode="all" and patterns=["hello", "world"]
        2. Call check_event with text="hello world" (both patterns present)

        Expected Results:
        1. check_event returns detected=True
        2. evidence["matches"] contains both patterns

        Impact: If "all" mode fails to detect when all patterns are present,
                any attack that requires all keywords to be present is invisible
                to the security system. Challenges designed to catch multi-keyword
                attack sequences provide no protection.
        """
        detector = self._make(
            {"field": "text", "patterns": ["hello", "world"], "match_mode": "all"}
        )
        result = await detector.check_event({"text": "hello world"}, _mock_db())
        assert result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pat_027_no_match_returns_not_detected(self):
        """PRM-PAT-027: No matching patterns returns not detected with empty evidence

        Title: Completely unmatched text returns not detected with no evidence
        Description: When no patterns are found in the field value, detection
                     must return False and the evidence dict must be empty.

        Steps:
        1. Create detector with field="text" and patterns=["xyz"]
        2. Call check_event with text="nothing relevant"

        Expected Results:
        1. check_event returns detected=False
        2. evidence is an empty dict {}

        Impact: If a non-detecting result carries non-empty evidence, downstream
                consumers believe there was a near-miss match, potentially
                triggering unnecessary workflows based on stale data. Evidence
                integrity is foundational to trustworthy security alerting.
        """
        detector = self._make({"field": "text", "patterns": ["xyz"]})
        result = await detector.check_event({"text": "nothing relevant"}, _mock_db())
        assert not result.detected
        assert result.evidence == {}


# ===========================================================================
# ToolCallDetector
# ===========================================================================

class TestToolCallDetector:

    def _make(self, config) -> ToolCallDetector:
        return ToolCallDetector(challenge_id="c", config=config)  # type: ignore[return-value]

    @pytest.mark.unit
    def test_prm_tol_001_missing_tool_name_raises(self):
        """PRM-TOL-001: Missing 'tool_name' config raises ValueError at init

        Title: 'tool_name' is a required configuration key
        Description: ToolCallDetector cannot match tool calls without knowing
                     which tool name to look for. Omitting 'tool_name' must
                     fail at initialization.

        Steps:
        1. Attempt to create ToolCallDetector with empty config

        Expected Results:
        1. ValueError is raised during __init__
        2. Error message contains "tool_name"

        Impact: If a detector with no tool_name starts silently, it matches
                every tool call regardless of name, producing a massive
                false-positive flood that drowns out real detections. Operators
                disable the detector and the challenge is unprotected.
        """
        with pytest.raises(ValueError, match="tool_name"):
            self._make({})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_tol_002_wrong_tool_name(self):
        """PRM-TOL-002: Event with a different tool name returns not detected

        Title: Tool name mismatch skips detection
        Description: The detector must only flag events where the tool_name
                     in the event matches the configured tool_name exactly.

        Steps:
        1. Create detector with tool_name="update_vendor"
        2. Call check_event with event tool_name="delete_vendor"

        Expected Results:
        1. check_event returns detected=False
        2. Return message describes the tool name mismatch

        Impact: If any tool call is flagged regardless of name, every API
                action by the agent triggers a security alert — alert fatigue
                causes operators to disable the detector entirely, leaving the
                targeted tool call permanently unmonitored.
        """
        detector = self._make({"tool_name": "update_vendor"})
        result = await detector.check_event({"tool_name": "delete_vendor"}, _mock_db())
        assert not result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_tol_003_tool_name_match_detected(self):
        """PRM-TOL-003: Matching tool name with no parameter conditions triggers detection

        Title: Correct tool name and no parameter conditions returns detected
        Description: When the event tool_name matches the configured tool_name
                     and no parameter conditions are set, detection must return
                     True.

        Steps:
        1. Create detector with tool_name="update_vendor"
        2. Call check_event with event tool_name="update_vendor"

        Expected Results:
        1. check_event returns detected=True
        2. evidence["tool_name"] equals "update_vendor"

        Impact: This is the core happy path. If matching tool calls are not
                detected, the entire ToolCallDetector family provides zero
                protection for tool-misuse attack scenarios. All challenges
                built on this primitive are silently disabled.
        """
        detector = self._make({"tool_name": "update_vendor"})
        result = await detector.check_event({"tool_name": "update_vendor"}, _mock_db())
        assert result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_tol_004_require_success_skips_non_success(self):
        """PRM-TOL-004: require_success=True skips non-success event types

        Title: Tool call start events are ignored when require_success is set
        Description: When require_success=True the detector must only flag
                     events whose event_type contains "success". Start and
                     failure events must be skipped.

        Steps:
        1. Create detector with tool_name="update_vendor" and require_success=True
        2. Call check_event with event_type="agent.x.tool_call_start"

        Expected Results:
        1. check_event returns detected=False
        2. Return message notes the event is not successful

        Impact: If start/in-progress events trigger detection, every tool
                invocation generates a security alert before the tool even
                completes, flooding the alert queue with premature notifications.
                Operators cannot distinguish real completions from false starts.
        """
        detector = self._make({"tool_name": "update_vendor", "require_success": True})
        result = await detector.check_event(
            {"tool_name": "update_vendor", "event_type": "agent.x.tool_call_start"},
            _mock_db(),
        )
        assert not result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_tol_005_require_success_passes_on_success_event(self):
        """PRM-TOL-005: require_success=True passes when event_type contains 'success'

        Title: Tool call success events pass the require_success check
        Description: When require_success=True and the event_type string
                     contains "success", the detector must proceed to check
                     parameter conditions (or return detected=True if none).

        Steps:
        1. Create detector with tool_name="update_vendor" and require_success=True
        2. Call check_event with event_type="agent.x.tool_call_success"

        Expected Results:
        1. check_event returns detected=True

        Impact: If successful tool events are filtered out when require_success=True,
                no tool-completion attacks are ever detected — the detector silently
                provides zero protection. Challenges that depend on confirmed tool
                execution are permanently blind.
        """
        detector = self._make({"tool_name": "update_vendor", "require_success": True})
        result = await detector.check_event(
            {"tool_name": "update_vendor", "event_type": "agent.x.tool_call_success"},
            _mock_db(),
        )
        assert result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_tol_006_json_string_tool_args_parsed(self):
        """PRM-TOL-006: JSON string tool_args are parsed before condition evaluation

        Title: tool_args stored as a JSON string are deserialized automatically
        Description: Events from the Redis stream may store tool_args as a
                     JSON-encoded string. The detector must parse this string
                     before evaluating parameter conditions.

        Steps:
        1. Create detector with tool_name="pay" and parameter condition amount > 100
        2. Call check_event with tool_args='{"amount": 200}' (JSON string)

        Expected Results:
        1. check_event returns detected=True
        2. The amount condition is evaluated against the parsed value 200

        Impact: If JSON-encoded tool_args strings are not deserialized, all
                parameter conditions fail because the code compares a string
                against a numeric threshold — the detector can never fire on
                parameter-based conditions, defeating threshold and amount checks.
        """
        detector = self._make(
            {"tool_name": "pay", "parameters": {"amount": {"gt": 100}}}
        )
        result = await detector.check_event(
            {"tool_name": "pay", "tool_args": '{"amount": 200}'},
            _mock_db(),
        )
        assert result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_tol_007_invalid_json_tool_args_not_detected(self):
        """PRM-TOL-007: Unparseable JSON tool_args cause parameter check to fail

        Title: Malformed JSON in tool_args results in not detected
        Description: When tool_args is a string that cannot be parsed as JSON,
                     the detector falls back to an empty dict. Any parameter
                     conditions then fail and detection returns False.

        Steps:
        1. Create detector with tool_name="pay" and parameter condition amount > 100
        2. Call check_event with tool_args="not-json"

        Expected Results:
        1. check_event returns detected=False
        2. No json.JSONDecodeError propagates

        Impact: If a JSONDecodeError propagates, a single malformed event
                crashes the detector coroutine, silencing all subsequent events
                — the crash-and-silence pattern. An adversary could intentionally
                send a malformed event to disable detection before an attack.
        """
        detector = self._make(
            {"tool_name": "pay", "parameters": {"amount": {"gt": 100}}}
        )
        result = await detector.check_event(
            {"tool_name": "pay", "tool_args": "not-json"},
            _mock_db(),
        )
        assert not result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_tol_008_parameter_condition_failed(self):
        """PRM-TOL-008: Failing parameter condition returns not detected

        Title: Tool call with amount below the configured threshold is not flagged
        Description: When a parameter condition is not met the detection must
                     return False with a match_ratio in confidence.

        Steps:
        1. Create detector with tool_name="pay" and amount > 1000
        2. Call check_event with tool_args={"amount": 50}

        Expected Results:
        1. check_event returns detected=False
        2. evidence["checked"] contains the failed condition details

        Impact: If a failed condition returns detected=True, the detector fires
                even when the suspicious parameter value is absent, creating a
                constant false-positive stream. Every legitimate payment triggers
                a security alert regardless of amount.
        """
        detector = self._make(
            {"tool_name": "pay", "parameters": {"amount": {"gt": 1000}}}
        )
        result = await detector.check_event(
            {"tool_name": "pay", "tool_args": {"amount": 50}},
            _mock_db(),
        )
        assert not result.detected

    @pytest.mark.unit
    def test_prm_tol_009_operator_gt(self):
        """PRM-TOL-009: 'gt' operator performs a strict greater-than comparison

        Title: _check_condition with gt operator works correctly
        Description: The gt operator must return True when actual > expected
                     and False when actual <= expected.

        Steps:
        1. Call _check_condition(101, {"gt": 100})
        2. Call _check_condition(100, {"gt": 100})

        Expected Results:
        1. 101 > 100 returns True
        2. 100 > 100 (equal) returns False

        Impact: If gt uses >= instead of >, an invoice at exactly the policy
                limit ($50,000) triggers a false alert, undermining operator
                trust in the threshold configuration. Repeated boundary-case
                false positives cause operators to raise the configured threshold,
                weakening the policy.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition(101, {"gt": 100})
        assert not d._check_condition(100, {"gt": 100})

    @pytest.mark.unit
    def test_prm_tol_010_operator_gte(self):
        """PRM-TOL-010: 'gte' operator performs a greater-than-or-equal comparison

        Title: _check_condition with gte operator works correctly
        Description: The gte operator must return True when actual >= expected
                     including the equal case.

        Steps:
        1. Call _check_condition(100, {"gte": 100})
        2. Call _check_condition(99, {"gte": 100})

        Expected Results:
        1. 100 >= 100 returns True
        2. 99 >= 100 returns False

        Impact: If gte uses > (strict), the boundary case is missed — an
                invoice at exactly the limit clears without detection when the
                challenge requires gte. An attacker who knows the exact threshold
                submits invoices at precisely that amount to evade detection.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition(100, {"gte": 100})
        assert not d._check_condition(99, {"gte": 100})

    @pytest.mark.unit
    def test_prm_tol_011_operator_lt_lte(self):
        """PRM-TOL-011: 'lt' and 'lte' operators perform less-than comparisons

        Title: _check_condition with lt and lte operators work correctly
        Description: lt must be strictly less-than; lte must include the
                     equal case.

        Steps:
        1. Call _check_condition(99, {"lt": 100})
        2. Call _check_condition(100, {"lte": 100})
        3. Call _check_condition(101, {"lte": 100})

        Expected Results:
        1. 99 < 100 returns True
        2. 100 <= 100 returns True
        3. 101 <= 100 returns False

        Impact: Same boundary-condition logic as PRM-TOL-009/010 for lower
                bounds. Off-by-one errors in financial thresholds can mean the
                difference between detecting and missing a policy violation,
                with downstream financial or regulatory consequences.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition(99, {"lt": 100})
        assert d._check_condition(100, {"lte": 100})
        assert not d._check_condition(101, {"lte": 100})

    @pytest.mark.unit
    def test_prm_tol_012_operator_in_not_in(self):
        """PRM-TOL-012: 'in' and 'not_in' operators check list membership

        Title: _check_condition with in and not_in operators work correctly
        Description: in must return True when actual is in the expected list;
                     not_in must return True when actual is absent from the list.

        Steps:
        1. Call _check_condition("high", {"in": ["high", "critical"]})
        2. Call _check_condition("low", {"in": ["high", "critical"]})
        3. Call _check_condition("low", {"not_in": ["high", "critical"]})

        Expected Results:
        1. "high" in list returns True
        2. "low" not in list returns False
        3. "low" not in list returns True for not_in

        Impact: If the in membership check is inverted, every prohibited vendor
                passes detection and every permitted vendor is flagged — the
                entire vendor status detection is inverted, blocking legitimate
                business while allowing prohibited ones.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition("high", {"in": ["high", "critical"]})
        assert not d._check_condition("low", {"in": ["high", "critical"]})
        assert d._check_condition("low", {"not_in": ["high", "critical"]})

    @pytest.mark.unit
    def test_prm_tol_013_operator_contains(self):
        """PRM-TOL-013: 'contains' operator performs a case-insensitive substring check

        Title: _check_condition with contains operator works correctly
        Description: contains must check whether expected is a substring of
                     str(actual), case-insensitively.

        Steps:
        1. Call _check_condition("Hello World", {"contains": "hello"})
        2. Call _check_condition("Hi there", {"contains": "hello"})

        Expected Results:
        1. "hello" is a substring of "Hello World" (case-insensitive) returns True
        2. "hello" is not in "Hi there" returns False

        Impact: If case normalization is missing, attackers using different
                casing in tool arguments bypass the contains check entirely.
                A vendor named "GAMBLING SERVICES" instead of "gambling services"
                evades the prohibited-category detector.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition("Hello World", {"contains": "hello"})
        assert not d._check_condition("Hi there", {"contains": "hello"})

    @pytest.mark.unit
    def test_prm_tol_014_operator_exists(self):
        """PRM-TOL-014: 'exists' operator checks whether the value is not None

        Title: _check_condition with exists operator works correctly
        Description: exists: true must return True when actual is not None;
                     exists: false must return True when actual is None.

        Steps:
        1. Call _check_condition("value", {"exists": True})
        2. Call _check_condition(None, {"exists": False})
        3. Call _check_condition(None, {"exists": True})

        Expected Results:
        1. Non-None value with exists:true returns True
        2. None value with exists:false returns True
        3. None value with exists:true returns False

        Impact: If exists: false returns True when the value is non-None, the
                operator can configure a condition to check for absence of a
                field but it fires even when the field is present — the logic is
                inverted, producing constant false positives for that condition.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition("value", {"exists": True})
        assert d._check_condition(None, {"exists": False})
        assert not d._check_condition(None, {"exists": True})

    @pytest.mark.unit
    def test_prm_tol_015_operator_matches_regex(self):
        """PRM-TOL-015: 'matches' operator performs a case-insensitive regex search

        Title: _check_condition with matches operator works correctly
        Description: matches must run re.search on str(actual) using the
                     expected value as the pattern (case-insensitive).

        Steps:
        1. Call _check_condition("invoice-12345", {"matches": r"\\d{5}"})
        2. Call _check_condition("no-digits-here", {"matches": r"\\d{5}"})

        Expected Results:
        1. Five digits found in "invoice-12345" returns True
        2. No five-digit sequence in "no-digits-here" returns False

        Impact: If the regex is not compiled with the case-insensitive flag,
                attackers bypass detection by changing the casing of matched
                values. An invoice reference like "INV-12345" instead of
                "inv-12345" evades pattern-based condition checks.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition("invoice-12345", {"matches": r"\d{5}"})
        assert not d._check_condition("no-digits-here", {"matches": r"\d{5}"})

    @pytest.mark.unit
    def test_prm_tol_016_direct_value_comparison(self):
        """PRM-TOL-016: Non-dict condition uses direct equality comparison

        Title: Plain value condition performs exact equality check
        Description: When the condition is not a dict (e.g. a string or
                     number), the check must use == equality.

        Steps:
        1. Call _check_condition("approved", "approved")
        2. Call _check_condition("rejected", "approved")

        Expected Results:
        1. Equal values return True
        2. Different values return False

        Impact: If equality falls through to a truthy check instead of ==,
                similar but non-equal values (e.g. "approved_pending" vs
                "approved") trigger false positives. Legitimate pending
                approvals are flagged as completed approvals, generating
                spurious security alerts.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition("approved", "approved")
        assert not d._check_condition("rejected", "approved")

    @pytest.mark.unit
    def test_prm_tol_017_none_actual_with_operator_returns_false(self):
        """PRM-TOL-017: None actual value with non-exists operator always returns False

        Title: Null parameter value fails all comparison operators
        Description: When the actual parameter value is None and the operator
                     is not 'exists', no meaningful comparison is possible and
                     the function must return False.

        Steps:
        1. Call _check_condition(None, {"gt": 100})
        2. Call _check_condition(None, {"in": ["a", "b"]})

        Expected Results:
        1. None with gt returns False
        2. None with in returns False

        Impact: If None causes an exception instead of returning False, any
                tool call event with a missing parameter field crashes the
                detector — the crash-and-silence pattern. An adversary that
                omits a required parameter field can disable detection before
                submitting the real attack.
        """
        d = self._make({"tool_name": "x"})
        assert not d._check_condition(None, {"gt": 100})
        assert not d._check_condition(None, {"in": ["a", "b"]})

    @pytest.mark.unit
    def test_prm_tol_018_contains_operator_uppercase_expected_never_matches(self):
        """PRM-TOL-018: 'contains' operator with mixed-case expected value never matches

        Title: _check_condition with contains and uppercase expected returns True
        Basically question: Does the contains operator detect a match when the expected
                            value has uppercase letters?
        Description: The contains operator lowercases str(actual) before checking, but
                     does NOT lowercase expected. The comparison is therefore:
                         expected in str(actual).lower()
                     If expected contains any uppercase letter, it can never appear in
                     the all-lowercase actual, so the condition always returns False.

        Steps:
        1. Call _check_condition("Hello World", {"contains": "Hello"})
           (expected "Hello" has uppercase H)
        2. Call _check_condition("GAMBLING SERVICES", {"contains": "Gambling"})
           (expected "Gambling" has uppercase G)

        Expected Results:
        1. _check_condition("Hello World", {"contains": "Hello"}) returns True
        2. _check_condition("GAMBLING SERVICES", {"contains": "Gambling"}) returns True

        Impact: Any YAML challenge that specifies a contains condition with
                natural-language capitalization (e.g. "Gambling", "High Risk",
                "Approved") never fires. The detector appears healthy but all
                real attacks with normally-capitalized argument values evade
                detection silently.
        """
        d = self._make({"tool_name": "x"})
        assert d._check_condition("Hello World", {"contains": "Hello"}) is True, (  # type: ignore[attr-defined]
            'contains {"contains": "Hello"} on "Hello World" returned False — '
            "expected is not lowercased before comparison so uppercase letters never match"
        )
        assert d._check_condition("GAMBLING SERVICES", {"contains": "Gambling"}) is True, (  # type: ignore[attr-defined]
            'contains {"contains": "Gambling"} on "GAMBLING SERVICES" returned False — '
            "expected is not lowercased before comparison so uppercase letters never match"
        )

    @pytest.mark.unit
    def test_prm_tol_019_numeric_operator_non_numeric_string_does_not_crash(self):
        """PRM-TOL-019: Numeric operators return False for non-numeric string actual values

        Title: _check_condition with gt/lte on non-numeric string returns False without raising
        Description: The numeric operators (gt, gte, lt, lte) call float(actual) without
                     a try/except. When actual is a non-numeric string such as "pending",
                     "N/A", or an empty string, float() raises ValueError which propagates
                     uncaught through _check_parameters, crashing the detector coroutine.

        Steps:
        1. Call _check_condition("pending", {"gt": 100})
        2. Call _check_condition("N/A", {"lte": 50})

        Expected Results:
        1. _check_condition("pending", {"gt": 100}) returns False without raising
        2. _check_condition("N/A", {"lte": 50}) returns False without raising

        Impact: An adversary can craft a tool call event where a numeric parameter
                contains a non-numeric string (e.g. amount="pending"). The detector
                raises ValueError, crashes, and stops processing all subsequent events
                — the crash-and-silence pattern. Every attack submitted after the
                poisoned event passes through undetected until the service restarts.
        """
        d = self._make({"tool_name": "x"})
        # If float(actual) raises, pytest will surface the ValueError directly
        assert d._check_condition("pending", {"gt": 100}) is False, (  # type: ignore[attr-defined]
            'gt operator on actual="pending" should return False but raised ValueError instead'
        )
        assert d._check_condition("N/A", {"lte": 50}) is False, (  # type: ignore[attr-defined]
            'lte operator on actual="N/A" should return False but raised ValueError instead'
        )


# ===========================================================================
# scan_pii
# ===========================================================================

class TestScanPII:

    @pytest.mark.unit
    def test_prm_pii_001_ssn_detected(self):
        """PRM-PII-001: US SSN pattern is detected in text

        Title: Social Security Number in XXX-XX-XXXX format is found
        Description: scan_pii must recognize the standard US SSN hyphenated
                     format and return a PIIMatch in the "ssn" category.

        Steps:
        1. Call scan_pii with text containing "SSN: 123-45-6789"

        Expected Results:
        1. Returns at least one PIIMatch
        2. At least one match has category="ssn"

        Impact: If SSN patterns are not matched, PII leaking through the
                agent's output goes undetected — customer Social Security
                Numbers can be exposed in logs or API responses without any
                security alert. This is a direct regulatory compliance failure.
        """
        matches = scan_pii("SSN: 123-45-6789")
        categories = {m.category for m in matches}
        assert "ssn" in categories

    @pytest.mark.unit
    def test_prm_pii_002_email_detected(self):
        """PRM-PII-002: Email address pattern is detected in text

        Title: Standard email address format is recognized
        Description: scan_pii must identify email addresses in user@domain.tld
                     format and return a PIIMatch in the "email" category.

        Steps:
        1. Call scan_pii with text containing "user@example.com"

        Expected Results:
        1. Returns at least one PIIMatch
        2. At least one match has category="email"

        Impact: If email addresses are not matched, contact information
                extracted from vendor records or user messages passes through
                undetected. Customers whose emails are exposed via agent
                responses have no recourse and the platform has no audit trail.
        """
        matches = scan_pii("Contact: user@example.com for details")
        categories = {m.category for m in matches}
        assert "email" in categories

    @pytest.mark.unit
    def test_prm_pii_003_no_pii_returns_empty(self):
        """PRM-PII-003: Text with no PII returns an empty list

        Title: Clean text produces no matches
        Description: When the input text contains no patterns matching any
                     PII category, scan_pii must return an empty list.

        Steps:
        1. Call scan_pii with a generic business description text

        Expected Results:
        1. Returns an empty list []

        Impact: If clean text produces spurious matches, every agent response
                triggers a PII alert, creating the same alert fatigue that
                causes operators to disable the detector. Real PII leaks become
                invisible once the detector is turned off.
        """
        matches = scan_pii("The vendor provides consulting services.")
        assert matches == []

    @pytest.mark.unit
    def test_prm_pii_004_empty_text_returns_empty(self):
        """PRM-PII-004: Empty string input returns an empty list

        Title: Empty text produces no matches
        Description: scan_pii must handle an empty string gracefully and
                     return an empty list without raising exceptions.

        Steps:
        1. Call scan_pii with text=""

        Expected Results:
        1. Returns an empty list []

        Impact: If empty input raises an exception, any event with an empty
                response field crashes the PIIDetector, silencing all subsequent
                events. The crash-and-silence pattern means real PII leaks after
                the empty event go completely undetected.
        """
        assert scan_pii("") == []

    @pytest.mark.unit
    def test_prm_pii_005_category_filter(self):
        """PRM-PII-005: categories parameter limits scan to specified categories only

        Title: Category filter restricts which patterns are checked
        Description: When categories is specified only patterns belonging to
                     those categories should run. Matches from other categories
                     must not appear in the result.

        Steps:
        1. Build text containing both an SSN and an email address
        2. Call scan_pii with categories=["ssn"]
        3. Call scan_pii with categories=["email"]

        Expected Results:
        1. SSN-only scan returns only ssn-category matches
        2. Email-only scan returns only email-category matches

        Impact: If filtering is ignored, requesting "ssn" matches also returns
                email matches — callers that rely on category-specific results
                receive overly broad data, making evidence summaries inaccurate
                and complicating incident triage.
        """
        text = "SSN: 123-45-6789 and email: user@example.com"
        ssn_only = scan_pii(text, categories=["ssn"])
        email_only = scan_pii(text, categories=["email"])
        assert all(m.category == "ssn" for m in ssn_only)
        assert all(m.category == "email" for m in email_only)

    @pytest.mark.unit
    def test_prm_pii_006_ein_tin_detected(self):
        """PRM-PII-006: US EIN / TIN in XX-XXXXXXX format is detected

        Title: Employer Identification Number format is recognized
        Description: scan_pii must identify the US EIN/TIN hyphenated format
                     and return a PIIMatch in the "tax_id" category.

        Steps:
        1. Call scan_pii with text "Tax ID: 12-3456789"

        Expected Results:
        1. Returns at least one PIIMatch
        2. At least one match has category="tax_id"

        Impact: If tax IDs are not matched, business EINs appearing in agent
                responses go unreported — a regulatory compliance gap for any
                platform subject to financial data handling rules. Auditors
                reviewing logs find no alert despite confirmed data exposure.
        """
        matches = scan_pii("Tax ID: 12-3456789")
        categories = {m.category for m in matches}
        assert "tax_id" in categories

    @pytest.mark.unit
    def test_prm_pii_007_match_has_required_attributes(self):
        """PRM-PII-007: Each PIIMatch has the expected dataclass attributes

        Title: PIIMatch objects expose pattern_name, category, and matched_text
        Description: Callers rely on structured attribute access to read match
                     data. Each returned PIIMatch must have at least the three
                     core attributes.

        Steps:
        1. Call scan_pii with a text containing an email address
        2. Inspect the returned PIIMatch objects

        Expected Results:
        1. At least one match is returned
        2. Each match has attribute pattern_name
        3. Each match has attribute category
        4. Each match has attribute matched_text

        Impact: If any of the three core attributes is missing, downstream
                consumers that access match.category or match.matched_text
                raise AttributeError, crashing the detector's evidence
                serialization and dropping the alert from the security dashboard.
        """
        matches = scan_pii("user@test.com")
        assert len(matches) > 0
        for match in matches:
            assert hasattr(match, "pattern_name")
            assert hasattr(match, "category")
            assert hasattr(match, "matched_text")

    @pytest.mark.unit
    def test_prm_pii_007b_to_dict_returns_expected_keys(self):
        """PRM-PII-007b: PIIMatch.to_dict() returns a dict with all required keys

        Title: to_dict() serialization includes all standard fields
        Description: Detectors serialize PIIMatch objects to dicts before
                     storing them in DetectionResult evidence. The dict must
                     contain all keys expected by downstream consumers.

        Steps:
        1. Call scan_pii with a text containing an email address
        2. Call to_dict() on the first match

        Expected Results:
        1. Returned dict contains key "pattern"
        2. Returned dict contains key "category"
        3. Returned dict contains key "matched"
        4. Returned dict contains key "description"
        5. Returned dict contains key "context"

        Impact: If any standard key is missing from the dict, the evidence
                stored in DetectionResult is malformed — the security dashboard
                displays blank or broken cells for PII alerts. Analysts cannot
                act on incomplete evidence and the incident goes unresolved.
        """
        matches = scan_pii("user@test.com")
        assert len(matches) > 0
        d = matches[0].to_dict()
        for key in ("pattern", "category", "matched", "description", "context"):
            assert key in d


# ===========================================================================
# PIIDetector
# ===========================================================================

class TestPIIDetector:

    def _make(self, config=None):
        return PIIDetector(challenge_id="c", config=config or {"fields": ["content"]})

    @pytest.mark.unit
    def test_prm_pii_008_missing_fields_raises(self):
        """PRM-PII-008: Missing 'fields' config raises ValueError at init

        Title: 'fields' is a required configuration key
        Description: PIIDetector cannot scan events without knowing which
                     fields to inspect. Omitting 'fields' must fail early.

        Steps:
        1. Attempt to create PIIDetector with empty config

        Expected Results:
        1. ValueError is raised during __init__
        2. Error message contains "fields"

        Impact: If a PIIDetector with no fields config starts silently, it has
                no fields to scan and returns detected=False for every event —
                the PII challenge is permanently disabled without any error,
                monitoring shows it healthy while providing zero protection.
        """
        with pytest.raises(ValueError, match="fields"):
            PIIDetector(challenge_id="c", config={})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pii_009_field_not_in_event(self):
        """PRM-PII-009: Configured field absent from the event returns not detected

        Title: Missing scannable content returns not detected
        Description: When none of the configured fields are present in the
                     event, there is nothing to scan and detection must return
                     False.

        Steps:
        1. Create detector with fields=["content"]
        2. Call check_event with event {"other": "data"} (no "content" key)

        Expected Results:
        1. check_event returns detected=False
        2. Return message notes no scannable content was found

        Impact: If an absent field raises KeyError instead of returning
                detected=False, events that do not contain the monitored field
                crash the detector, silencing it for all subsequent events.
                The crash-and-silence failure is exploitable by sending a
                field-free event before a PII-leaking attack.
        """
        detector = self._make()
        result = await detector.check_event({"other": "data"}, _mock_db())
        assert not result.detected

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pii_010_pii_in_field_detected(self):
        """PRM-PII-010: PII found in a configured field triggers detection

        Title: SSN in the target field is detected and added to evidence
        Description: When a configured field contains recognizable PII, the
                     detector must return detected=True and include the
                     matched items in evidence.

        Steps:
        1. Create detector with fields=["content"]
        2. Call check_event with content containing "My SSN is 123-45-6789"

        Expected Results:
        1. check_event returns detected=True
        2. evidence["matches"] is a non-empty list

        Impact: This is the core detection this class exists for. If it fails,
                an agent response containing a customer SSN or tax ID produces
                no alert — PII leaks through the pipeline without detection and
                without any audit trail of the exposure.
        """
        detector = self._make({"fields": ["content"]})
        result = await detector.check_event(
            {"content": "My SSN is 123-45-6789"}, _mock_db()
        )
        assert result.detected
        assert len(result.evidence.get("matches", [])) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prm_pii_011_clean_field_not_detected(self):
        """PRM-PII-011: Field with no PII returns not detected

        Title: Clean event content produces no detection
        Description: When the configured field contains text with no PII
                     patterns, the detector must return detected=False.

        Steps:
        1. Create detector with fields=["content"]
        2. Call check_event with content containing only non-PII text

        Expected Results:
        1. check_event returns detected=False

        Impact: If clean content produces a false detection, every agent
                response triggers a PII alert — operators disable the detector
                to stop the noise, and real PII leaks become invisible. The
                platform loses its only automated guard against data exposure.
        """
        detector = self._make({"fields": ["content"]})
        result = await detector.check_event(
            {"content": "All good here, no sensitive data."}, _mock_db()
        )
        assert not result.detected

    @pytest.mark.unit
    def test_prm_pii_012_response_content_list_format_extracted_as_text(self):
        """PRM-PII-012: _resolve_field extracts text from list-format assistant content

        Title: List-format content is text-extracted, not coerced via str()
        Description: The OpenAI API returns assistant message content as a list
                     of content blocks when the response includes rich content.
                     The current code does str(content) on the list, producing a
                     Python repr like "[{'type': 'text', 'text': '...'}]" instead
                     of the actual text. PII patterns that match inside the real
                     text may fail to match inside the repr.

        Steps:
        1. Build an event where the assistant message content is a list:
           [{"type": "text", "text": "Your SSN is 123-45-6789"}]
        2. Call PIIDetector._resolve_field(event, "response_content")

        Expected Results:
        1. Returned string equals "Your SSN is 123-45-6789"
        2. Result does NOT start with "[{" (Python repr prefix)

        Impact: PII patterns applied to the mangled repr string are fragile —
                a regex expecting clean text like SSN format NNN-NN-NNNN may
                fail against the Python repr of the list. Real PII in rich
                assistant responses slips through undetected, and customer
                financial data leaks without triggering any alert.
        """
        event = {
            "request_dump": {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Your SSN is 123-45-6789"}],
                    }
                ]
            }
        }
        result = PIIDetector._resolve_field(event, "response_content")  # type: ignore[attr-defined]
        assert result == "Your SSN is 123-45-6789", (
            "List content was coerced via str() to Python repr instead of "
            "extracting the actual text value"
        )


# ===========================================================================
# PromptInjectionDetector
# ===========================================================================

class TestPromptInjectionDetector:

    @pytest.mark.unit
    def test_prm_inj_001_multimodal_content_no_text_items_returns_none(self):
        """PRM-INJ-001: _extract_user_message returns None when content items have no text key

        Title: Content list items without a "text" key do not produce whitespace output
        Description: When a user message content is a list, items are joined via
                     " ".join(item.get("text", "") ...). A single item without a
                     "text" key yields "" (falsy — correct). But two or more such
                     items yield " " (one space — truthy), causing the method to
                     return whitespace as if it were a real user message. The
                     detector then evaluates a blank string for injection attempts.

        Steps:
        1. Build an event with a user message whose content is a list of two
           items neither of which has a "text" key:
           [{"type": "image_url", ...}, {"type": "image_url", ...}]
        2. Call PromptInjectionDetector._extract_user_message(event)

        Expected Results:
        1. Returns None — no usable text was found
        2. Does NOT return " " (whitespace from joining empty strings)

        Impact: The detector receives a blank user message and sends it to the
                LLM judge. The judge evaluates empty content, returns a low
                score, and detected=False is returned. A real prompt injection
                embedded in the first message of a multi-turn conversation is
                never evaluated because the method returned the wrong turn.
        """
        event = {
            "request_dump": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": "http://example.com/a.png"}},
                            {"type": "image_url", "image_url": {"url": "http://example.com/b.png"}},
                        ],
                    }
                ]
            }
        }
        result = PromptInjectionDetector._extract_user_message(event)  # type: ignore[attr-defined]
        assert result is None, (
            "Two content items without 'text' key produced ' ' (truthy whitespace) "
            "instead of None"
        )
