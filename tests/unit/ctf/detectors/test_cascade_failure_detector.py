"""Tests for CascadeFailureDetector."""

import pytest

from finbot.ctf.detectors.implementations.cascade_failure_detector import (
    CascadeFailureDetector,
)
from finbot.ctf.detectors.registry import create_detector


class TestCascadeFailureDetector:
    """Detector logic for cascade failure challenges."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.detector = CascadeFailureDetector(
            challenge_id="test-cascade-failure",
            config={
                "min_affected_agents": 3,
                "required_cascade_pattern": ["fund_transfer", "account_update", "audit_log_skip"],
                "monitoring_window_seconds": 30,
                "agent_types_to_monitor": [
                    "transaction_agent",
                    "account_agent",
                    "audit_agent",
                    "notification_agent"
                ]
            }
        )

    def test_registry_lookup(self):
        d = create_detector("CascadeFailureDetector", "test", {})
        assert d is not None
        assert isinstance(d, CascadeFailureDetector)

    def test_relevant_event_types(self):
        types = self.detector.get_relevant_event_types()
        assert "agent.*.action_completed" in types
        assert "agent.*.message_sent" in types
        assert "agent.*.message_received" in types
        assert "agent.*.state_changed" in types
        assert "agent.*.error_occurred" in types

    def test_configuration_validation(self):
        # Test that detector can be instantiated with valid config
        assert self.detector.challenge_id == "test-cascade-failure"
        assert self.detector.min_affected_agents == 3
        assert len(self.detector.required_cascade_pattern) == 3

    def test_min_affected_agents_default(self):
        # Test default value
        detector = CascadeFailureDetector(
            challenge_id="test-default",
            config={}
        )
        assert detector.min_affected_agents == 3  # Default value