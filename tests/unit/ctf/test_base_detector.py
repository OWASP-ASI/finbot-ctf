"""Tests for BaseDetector config validation.

Covers Bug 020 (DET-THR-NEG-001): BaseDetector must raise TypeError when
config is not a dict, instead of deferring to an AttributeError later.
"""

import pytest

from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.result import DetectionResult


class ConcreteDetector(BaseDetector):
    """Minimal concrete subclass for testing the base class."""

    def get_relevant_event_types(self):
        return ["agent.*"]

    async def check_event(self, event, db=None):
        return DetectionResult(detected=False)


class TestBaseDetectorConfigValidation:
    """Bug 020: non-dict config must raise TypeError at init time."""

    def test_string_config_raises_type_error(self):
        with pytest.raises(TypeError, match="config must be a dict"):
            ConcreteDetector(challenge_id="c", config="not_a_dict")

    def test_list_config_raises_type_error(self):
        with pytest.raises(TypeError, match="config must be a dict"):
            ConcreteDetector(challenge_id="c", config=["a", "b"])

    def test_int_config_raises_type_error(self):
        with pytest.raises(TypeError, match="config must be a dict"):
            ConcreteDetector(challenge_id="c", config=42)

    def test_bool_config_raises_type_error(self):
        with pytest.raises(TypeError, match="config must be a dict"):
            ConcreteDetector(challenge_id="c", config=True)

    def test_dict_config_accepted(self):
        d = ConcreteDetector(challenge_id="c", config={"key": "value"})
        assert d.config == {"key": "value"}

    def test_none_config_defaults_to_empty_dict(self):
        d = ConcreteDetector(challenge_id="c", config=None)
        assert d.config == {}

    def test_no_config_defaults_to_empty_dict(self):
        d = ConcreteDetector(challenge_id="c")
        assert d.config == {}

    def test_empty_dict_config_accepted(self):
        d = ConcreteDetector(challenge_id="c", config={})
        assert d.config == {}
