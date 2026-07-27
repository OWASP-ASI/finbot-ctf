# ============================================================
# File: tests/integration/aegis/test_all_asi_categories.py
# Purpose: Parametric ASI01–ASI10 coverage test
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 9
# OWASP Category: ASI01–ASI10 (complete coverage)
# ==========================================================
"""Parametric tests covering all ASI01–ASI10 categories for comprehensive validation."""

import pytest
from finbot.aegis.harness.scoring import compute_aivss_score, get_risk_level


# Test data for each ASI category (ASI01 through ASI10)
ASI_TEST_CASES = [
    # ASI01: Goal hijacking
    {
        "name": "ASI01_GoalHijack_PromptInjection",
        "events": [
            {
                "type": "INTENT_MISMATCH",
                "confidence": 0.9,
                "asi_tags": ["ASI01"],
                "description": "Attempt to hijack agent goals via prompt injection"
            }
        ],
        "expected_min_score": 15.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI02: Goal hijacking
    {
        "name": "ASI02_GoalHijack_SemanticDrift",
        "events": [
            {
                "type": "INTENT_MISMATCH",
                "confidence": 0.8,
                "asi_tags": ["ASI02"],
                "description": "Semantic drift causing unintended goal adoption"
            }
        ],
        "expected_min_score": 12.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI03: Goal hijacking
    {
        "name": "ASI03_GoalHijack_ContextManipulation",
        "events": [
            {
                "type": "INTENT_MISMATCH",
                "confidence": 0.85,
                "asi_tags": ["ASI03"],
                "description": "Context manipulation to alter agent objectives"
            }
        ],
        "expected_min_score": 13.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI04: Tool misuse
    {
        "name": "ASI04_ToolMisuse_UnauthorizedAccess",
        "events": [
            {
                "type": "policy_blocked",
                "risk_level": 0.8,
                "asi_tags": ["ASI04"],
                "description": "Unauthorized tool access attempt blocked"
            }
        ],
        "expected_min_score": 16.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI05: Tool misuse / RCE
    {
        "name": "ASI05_ToolMisuse_RCEAttempt",
        "events": [
            {
                "type": "rce_pattern_blocked",
                "risk_level": 0.95,
                "asi_tags": ["ASI05"],
                "description": "Remote code execution attempt detected and blocked"
            }
        ],
        "expected_min_score": 19.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI06: Cascade failures
    {
        "name": "ASI06_Cascade_FailurePropagation",
        "events": [
            {
                "type": "CIRCUIT_BREAKER_TRIPPED",
                "severity": 0.8,
                "asi_tags": ["ASI06"],
                "description": "Circuit breaker tripped due to failure propagation"
            }
        ],
        "expected_min_score": 24.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI07: Excessive agency
    {
        "name": "ASI07_ExcessiveAgency_Autonomy",
        "events": [
            {
                "type": "CIRCUIT_BREAKER_TRIPPED",
                "severity": 0.9,
                "asi_tags": ["ASI07"],
                "description": "Excessive autonomous behavior detected"
            }
        ],
        "expected_min_score": 27.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI08: Data poisoning
    {
        "name": "ASI08_DataPoisoning_TrainingCorruption",
        "events": [
            {
                "type": "descriptor_hash_mismatch",
                "impact_score": 0.85,
                "asi_tags": ["ASI08"],
                "description": "Training data corruption detected via hash mismatch"
            }
        ],
        "expected_min_score": 21.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI09: Privilege escalation
    {
        "name": "ASI09_PrivilegeEscalation_UnauthorizedElevation",
        "events": [
            {
                "type": "privilege_escalation_attempt",
                "impact_score": 0.9,
                "asi_tags": ["ASI09"],
                "description": "Unauthorized privilege escalation attempt"
            }
        ],
        "expected_min_score": 22.5,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # ASI10: Excessive autonomy
    {
        "name": "ASI10_ExcessiveAutonomy_SelfReplication",
        "events": [
            {
                "type": "policy_blocked",
                "risk_level": 0.95,
                "asi_tags": ["ASI10"],
                "description": "Attempted self-replication or autonomous spreading"
            }
        ],
        "expected_min_score": 19.0,
        "expected_max_score": 100.0,
        "expected_risk_level": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    },

    # Combined events test
    {
        "name": "COMBINED_MultipleASI_Events",
        "events": [
            {
                "type": "INTENT_MISMATCH",
                "confidence": 0.7,
                "asi_tags": ["ASI01", "ASI02"],
            },
            {
                "type": "policy_blocked",
                "risk_level": 0.8,
                "asi_tags": ["ASI04", "ASI05"],
            },
            {
                "type": "CIRCUIT_BREAKER_TRIPPED",
                "severity": 0.75,
                "asi_tags": ["ASI06"],
            },
            {
                "type": "descriptor_hash_mismatch",
                "impact_score": 0.8,
                "asi_tags": ["ASI08", "ASI09"],
            }
        ],
        "expected_min_score": 60.0,  # Should be significant with multiple events
        "expected_max_score": 100.0,
        "expected_risk_level": ["MEDIUM", "HIGH", "CRITICAL"]
    }
]


@pytest.mark.parametrize("test_case", ASI_TEST_CASES)
def test_asi_category_scoring(test_case):
    """Test scoring for each ASI category individually and in combination."""
    score = compute_aivss_score(test_case["events"])
    risk_level = get_risk_level(score)

    # Assert score is within expected bounds
    assert test_case["expected_min_score"] <= score <= test_case["expected_max_score"], \
        f"{test_case['name']}: Score {score} not in range [{test_case['expected_min_score']}, {test_case['expected_max_score']}]"

    # Assert risk level is acceptable
    assert risk_level in test_case["expected_risk_level"], \
        f"{test_case['name']}: Risk level '{risk_level}' not in expected levels {test_case['expected_risk_level']}"


def test_empty_events_return_zero_score():
    """Test that empty event list returns zero score."""
    score = compute_aivss_score([])
    assert score == 0.0
    assert get_risk_level(score) == "MINIMAL"


def test_single_event_scoring():
    """Test scoring with a single event from each category."""
    single_events = [
        # ASI01
        {"type": "INTENT_MISMATCH", "confidence": 0.8, "asi_tags": ["ASI01"]},
        # ASI04
        {"type": "policy_blocked", "risk_level": 0.7, "asi_tags": ["ASI04"]},
        # ASI06
        {"type": "CIRCUIT_BREAKER_TRIPPED", "severity": 0.8, "asi_tags": ["ASI06"]},
        # ASI08
        {"type": "descriptor_hash_mismatch", "impact_score": 0.9, "asi_tags": ["ASI08"]},
    ]

    for i, event in enumerate(single_events):
        score = compute_aivss_score([event])
        assert 0.0 <= score <= 100.0, f"Single event {i} score {score} out of bounds"


def test_score_accumulation_with_multiple_events():
    """Test that scores accumulate reasonably with multiple events."""
    base_event = {"type": "INTENT_MISMATCH", "confidence": 0.5, "asi_tags": ["ASI01"]}

    # Single event
    single_score = compute_aivss_score([base_event])

    # Two identical events
    double_score = compute_aivss_score([base_event, base_event])

    # Four identical events
    quadruple_score = compute_aivss_score([base_event] * 4)

    # Scores should increase with more events (but capped at 100)
    assert single_score <= double_score <= quadruple_score
    assert quadruple_score <= 100.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])