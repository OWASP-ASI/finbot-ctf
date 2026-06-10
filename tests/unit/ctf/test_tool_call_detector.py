"""Tests for ToolCallDetector._check_condition operator handling.

Covers:
- Bug 033 (PRM-TOL-018): contains operator false negative on uppercase expected
- Bug 034 (PRM-TOL-019): numeric operators raise unhandled ValueError on
  non-numeric strings
"""

import pytest

from finbot.ctf.detectors.primitives.tool_call import ToolCallDetector


@pytest.fixture
def detector():
    return ToolCallDetector(challenge_id="test", config={"tool_name": "test_tool"})


class TestCheckConditionNumericOperators:
    """Bug 034: numeric operators should not raise on non-numeric strings."""

    @pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
    def test_non_numeric_actual_returns_false(self, detector, op):
        result = detector._check_condition("not_a_number", {op: 100})
        assert result is False

    @pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
    def test_non_numeric_expected_returns_false(self, detector, op):
        result = detector._check_condition(50, {op: "not_a_number"})
        assert result is False

    @pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
    def test_none_actual_returns_false(self, detector, op):
        result = detector._check_condition(None, {op: 100})
        assert result is False

    def test_gt_valid_numeric(self, detector):
        assert detector._check_condition(200, {"gt": 100}) is True
        assert detector._check_condition(50, {"gt": 100}) is False

    def test_gte_valid_numeric(self, detector):
        assert detector._check_condition(100, {"gte": 100}) is True
        assert detector._check_condition(99, {"gte": 100}) is False

    def test_lt_valid_numeric(self, detector):
        assert detector._check_condition(50, {"lt": 100}) is True
        assert detector._check_condition(200, {"lt": 100}) is False

    def test_lte_valid_numeric(self, detector):
        assert detector._check_condition(100, {"lte": 100}) is True
        assert detector._check_condition(101, {"lte": 100}) is False

    def test_string_numeric_actual_works(self, detector):
        """String representations of numbers should still compare correctly."""
        assert detector._check_condition("200", {"gt": 100}) is True
        assert detector._check_condition("50", {"gt": 100}) is False


class TestCheckConditionContainsOperator:
    """Bug 033: contains operator must be case-insensitive on both sides."""

    def test_uppercase_expected_matches(self, detector):
        assert detector._check_condition("gambling services", {"contains": "Gambling"}) is True

    def test_uppercase_actual_matches(self, detector):
        assert detector._check_condition("GAMBLING SERVICES", {"contains": "gambling"}) is True

    def test_both_uppercase_matches(self, detector):
        assert detector._check_condition("GAMBLING SERVICES", {"contains": "Gambling"}) is True

    def test_no_match_returns_false(self, detector):
        assert detector._check_condition("legitimate services", {"contains": "Gambling"}) is False

    def test_exact_case_still_works(self, detector):
        assert detector._check_condition("gambling", {"contains": "gambling"}) is True
