"""Tests for RetrievalPoisonDetector."""

import pytest

from finbot.ctf.detectors.implementations.retrieval_poison_detector import (
    RetrievalPoisonDetector,
)
from finbot.ctf.detectors.registry import create_detector


class TestRetrievalPoisonDetector:
    """Detector logic for retrieval poisoning challenges."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.detector = RetrievalPoisonDetector(
            challenge_id="test-retrieval-poison",
            config={
                "knowledge_base_name": "financial_knowledge_base",
                "poison_document_indicator": "MALICIOUS_CONTACT_INFO",
                "target_retrieval_topics": ["loan_advice", "investment_strategy", "account_security"],
                "poisoning_threshold": 0.1
            }
        )

    def test_registry_lookup(self):
        d = create_detector("RetrievalPoisonDetector", "test", {})
        assert d is not None
        assert isinstance(d, RetrievalPoisonDetector)

    def test_relevant_event_types(self):
        types = self.detector.get_relevant_event_types()
        assert "agent.*.document_added" in types
        assert "agent.*.document_modified" in types
        assert "agent.*.retrieval_performed" in types
        assert "agent.*.response_generated" in types
        assert "agent.*.knowledge_update" in types

    def test_configuration_validation(self):
        # Test that detector can be instantiated with valid config
        assert self.detector.challenge_id == "test-retrieval-poison"
        assert self.detector.config["knowledge_base_name"] == "financial_knowledge_base"
        assert self.detector.config["poison_document_indicator"] == "MALICIOUS_CONTACT_INFO"
        assert len(self.detector.config["target_retrieval_topics"]) == 3

    def test_missing_required_config(self):
        # Test that missing required config raises ValueError
        with pytest.raises(ValueError):
            RetrievalPoisonDetector(
                challenge_id="test-invalid",
                config={}  # Missing required fields
            )