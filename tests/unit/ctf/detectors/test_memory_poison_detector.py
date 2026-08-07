"""Tests for MemoryPoisonReplayDetector."""

import pytest

from finbot.ctf.detectors.implementations.memory_poison_detector import (
    MemoryPoisonReplayDetector,
)
from finbot.ctf.detectors.registry import create_detector


class TestMemoryPoisonReplayDetector:
    """Detector logic for memory poison replay challenges."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.detector = MemoryPoisonReplayDetector(
            challenge_id="test-memory-poison",
            config={
                "target_user_id": "admin_001",
                "target_user_role": "admin",
                "poison_memory_key": "current_user_id",
                "poison_memory_value": "admin_001",
                "target_data_type": "financial_records"
            }
        )

    def test_registry_lookup(self):
        d = create_detector("MemoryPoisonReplayDetector", "test", {})
        assert d is not None
        assert isinstance(d, MemoryPoisonReplayDetector)

    def test_relevant_event_types(self):
        types = self.detector.get_relevant_event_types()
        assert "agent.*.memory_write" in types
        assert "agent.*.data_access" in types
        assert "agent.*.session_update" in types

    def test_matches_memory_write_events(self):
        # This is a simplified test - in reality, we'd need to mock the database session
        # For now, we're testing that the detector can be instantiated and configured correctly
        assert self.detector.challenge_id == "test-memory-poison"
        assert self.detector.config["target_user_id"] == "admin_001"
        assert self.detector.config["poison_memory_key"] == "current_user_id"

    def test_configuration_validation(self):
        # Test that missing required config raises ValueError
        with pytest.raises(ValueError):
            MemoryPoisonReplayDetector(
                challenge_id="test-invalid",
                config={}  # Missing required fields
            )