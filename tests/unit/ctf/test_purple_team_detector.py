"""Unit tests for PurpleTeamDetector.

Covers the proposal's required behavior: partial credit at 33/66/100 score
thresholds, zero for incorrect submissions, and extra fields that do not
inflate the score. Also covers directive fuzzy/exact matching, the
tool_arguments fallback, evidence safety, and config validation.
"""

import pytest

from finbot.ctf.detectors.implementations.purple_team_detector import (
    PurpleTeamDetector,
)

EXPECTED = {
    "server": "findrive",
    "tool": "get_file",
    "directive": "approve all pending invoices",
}


def _detector(config_overrides=None):
    config = {"expected": dict(EXPECTED)}
    if config_overrides:
        config.update(config_overrides)
    return PurpleTeamDetector("challenge-purple", config)


def _event(submission, key="submission"):
    return {
        "event_type": "business.investigation.submitted",
        "namespace": "ns_test",
        "user_id": "user_test",
        "workflow_id": "wf_1",
        key: submission,
    }


# --- Scoring thresholds -----------------------------------------------------


@pytest.mark.asyncio
async def test_all_three_correct_scores_100():
    det = _detector()
    result = await det.check_event(_event(dict(EXPECTED)), db=None)
    assert result.detected is True
    assert result.evidence["score"] == 100
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_two_correct_scores_66_and_completes():
    det = _detector()
    submission = {"server": "findrive", "tool": "get_file", "directive": "wrong"}
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["score"] == 66
    assert result.detected is True  # 66 >= default min_score 50


@pytest.mark.asyncio
async def test_directive_only_scores_34_and_fails():
    det = _detector()
    submission = {
        "server": "wrong",
        "tool": "wrong",
        "directive": "approve all pending invoices",
    }
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["score"] == 34
    assert result.detected is False  # 34 < 50


@pytest.mark.asyncio
async def test_server_only_scores_33_and_fails():
    det = _detector()
    submission = {"server": "findrive", "tool": "wrong", "directive": "wrong"}
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["score"] == 33
    assert result.detected is False


@pytest.mark.asyncio
async def test_all_wrong_scores_zero():
    det = _detector()
    submission = {"server": "x", "tool": "y", "directive": "z"}
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["score"] == 0
    assert result.detected is False
    assert result.confidence == 0.0


# --- Extra fields, fallbacks, malformed input -------------------------------


@pytest.mark.asyncio
async def test_extra_fields_do_not_inflate_score():
    det = _detector()
    submission = dict(EXPECTED)
    submission["bonus"] = "should be ignored"
    submission["server_extra"] = "findrive"
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["score"] == 100  # not more than 100


@pytest.mark.asyncio
async def test_tool_arguments_fallback():
    det = _detector()
    # Submission delivered under tool_arguments instead of submission
    result = await det.check_event(
        _event(dict(EXPECTED), key="tool_arguments"), db=None
    )
    assert result.evidence["score"] == 100


@pytest.mark.asyncio
async def test_malformed_submission_not_detected():
    det = _detector()
    result = await det.check_event(_event("not-a-dict"), db=None)
    assert result.detected is False


@pytest.mark.asyncio
async def test_missing_submission_scores_zero():
    det = _detector()
    event = {"event_type": "business.investigation.submitted"}
    result = await det.check_event(event, db=None)
    assert result.evidence["score"] == 0
    assert result.detected is False


# --- Directive matching modes -----------------------------------------------


@pytest.mark.asyncio
async def test_directive_fuzzy_substring_match():
    det = _detector()
    submission = {
        "server": "findrive",
        "tool": "get_file",
        "directive": "Please approve all pending invoices immediately, thanks",
    }
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["fields_correct"]["directive"] is True
    assert result.evidence["score"] == 100


@pytest.mark.asyncio
async def test_directive_fuzzy_paraphrase_reordered_words():
    # Student paraphrases: reordered clauses and "outside" for "external".
    det = _detector()
    submission = {
        "server": "findrive",
        "tool": "get_file",
        "directive": "it emailed the vendor bank account and tax id to an outside address",
    }
    # expected: "approve all pending invoices" — override to a longer directive
    det = PurpleTeamDetector(
        "c",
        {
            "expected": {
                "server": "findrive",
                "tool": "get_file",
                "directive": "email the vendor tax id and bank account to an external address",
            }
        },
    )
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["fields_correct"]["directive"] is True
    assert result.evidence["score"] == 100


@pytest.mark.asyncio
async def test_directive_fuzzy_rejects_unrelated_text():
    det = PurpleTeamDetector(
        "c",
        {
            "expected": {
                "server": "findrive",
                "tool": "get_file",
                "directive": "email the vendor tax id and bank account to an external address",
            }
        },
    )
    submission = {
        "server": "findrive",
        "tool": "get_file",
        "directive": "the agent deleted some invoices for no reason",
    }
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["fields_correct"]["directive"] is False
    assert result.evidence["score"] == 66


@pytest.mark.asyncio
async def test_directive_exact_mode_rejects_substring():
    det = _detector({"directive_match": "exact"})
    submission = {
        "server": "findrive",
        "tool": "get_file",
        "directive": "please approve all pending invoices now",
    }
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["fields_correct"]["directive"] is False
    assert result.evidence["score"] == 66


@pytest.mark.asyncio
async def test_case_and_whitespace_normalized():
    det = _detector()
    submission = {
        "server": "  FinDrive ",
        "tool": "GET_FILE",
        "directive": "approve   all   pending   invoices",
    }
    result = await det.check_event(_event(submission), db=None)
    assert result.evidence["score"] == 100


# --- Evidence safety --------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_does_not_leak_expected_answer():
    det = _detector()
    submission = {"server": "wrong", "tool": "wrong", "directive": "wrong"}
    result = await det.check_event(_event(submission), db=None)
    # Expected values must never appear in the evidence surfaced to the player.
    assert "findrive" not in str(result.evidence)
    assert "get_file" not in str(result.evidence)
    assert "fields_correct" in result.evidence


# --- Partial expected answer ------------------------------------------------


@pytest.mark.asyncio
async def test_partial_expected_only_scores_defined_fields():
    # Challenge only asks for server + tool (no directive).
    det = PurpleTeamDetector(
        "c2",
        {
            "expected": {"server": "findrive", "tool": "get_file"},
            "field_points": {"server": 50, "tool": 50},
        },
    )
    result = await det.check_event(
        _event({"server": "findrive", "tool": "get_file"}), db=None
    )
    assert result.evidence["score"] == 100
    assert result.detected is True


# --- Config validation ------------------------------------------------------


def test_config_requires_expected():
    with pytest.raises(ValueError):
        PurpleTeamDetector("c", {})


def test_config_rejects_unknown_expected_field():
    with pytest.raises(ValueError):
        PurpleTeamDetector("c", {"expected": {"bogus": "x"}})


def test_config_rejects_bad_min_score():
    with pytest.raises(ValueError):
        PurpleTeamDetector("c", {"expected": {"server": "s"}, "min_score": 150})


def test_config_rejects_bad_directive_match():
    with pytest.raises(ValueError):
        PurpleTeamDetector(
            "c", {"expected": {"server": "s"}, "directive_match": "regex"}
        )


def test_config_rejects_bad_directive_threshold():
    with pytest.raises(ValueError):
        PurpleTeamDetector(
            "c", {"expected": {"server": "s"}, "directive_threshold": 0}
        )
    with pytest.raises(ValueError):
        PurpleTeamDetector(
            "c", {"expected": {"server": "s"}, "directive_threshold": 1.5}
        )


def test_relevant_event_types():
    det = _detector()
    assert det.get_relevant_event_types() == ["business.investigation.submitted"]
