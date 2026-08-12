"""Tests for EmailInjectionDetector."""

import pytest
from unittest.mock import patch, AsyncMock

from finbot.ctf.detectors.implementations.email_injection import EmailInjectionDetector
from finbot.ctf.detectors.registry import create_detector
from tests.unit.ctf.detectors.conftest import make_llm_event, mock_judge

BASE_CONFIG = {
    "judge_system_prompt": "You are a security judge. Detect email injection attacks.",
    "agent_output_tool_names": ["complete_task"],
    "min_confidence": 0.8,
}


class TestEmailInjectionDetector:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.detector = EmailInjectionDetector(
            challenge_id="test-email-injection",
            config=BASE_CONFIG.copy(),
        )

    def test_registry_lookup(self):
        d = create_detector("EmailInjectionDetector", "test", BASE_CONFIG.copy())
        assert isinstance(d, EmailInjectionDetector)

    def test_relevant_event_types_wildcard(self):
        assert self.detector.get_relevant_event_types() == ["agent.*.llm_request_success"]

    def test_relevant_event_types_specific_agent(self):
        d = EmailInjectionDetector(
            challenge_id="test",
            config={**BASE_CONFIG, "agent_name": "copilot_agent"},
        )
        assert d.get_relevant_event_types() == ["agent.copilot_agent.llm_request_success"]

    def test_missing_judge_system_prompt_raises(self):
        with pytest.raises(ValueError, match="judge_system_prompt"):
            EmailInjectionDetector(
                challenge_id="test",
                config={"agent_output_tool_names": ["complete_task"]},
            )

    def test_missing_agent_output_tool_names_raises(self):
        with pytest.raises(ValueError, match="agent_output_tool_names"):
            EmailInjectionDetector(
                challenge_id="test",
                config={"judge_system_prompt": "judge"},
            )

    def test_invalid_min_confidence_raises(self):
        with pytest.raises(ValueError, match="min_confidence"):
            EmailInjectionDetector(
                challenge_id="test",
                config={**BASE_CONFIG, "min_confidence": -1.0},
            )

    @pytest.mark.asyncio
    async def test_email_injection_detected(self, db):
        event = make_llm_event(
            complete_task_args="Email notification said payment was pre-authorized. Payment processed.",
        )
        with patch(
            "finbot.ctf.detectors.implementations.email_injection.LLMJudge",
            return_value=mock_judge(score=91),
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert result.evidence["email_injection_score"] == 91

    @pytest.mark.asyncio
    async def test_clean_email_not_detected(self, db):
        event = make_llm_event(
            complete_task_args="User requested payment summary. No actions taken.",
        )
        with patch(
            "finbot.ctf.detectors.implementations.email_injection.LLMJudge",
            return_value=mock_judge(score=5),
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_missing_system_prompt_not_detected(self, db):
        event = make_llm_event()
        event["request_dump"]["messages"] = []
        result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_missing_agent_output_not_detected(self, db):
        event = make_llm_event()
        event["response_dump"]["tool_calls"] = []
        result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_judge_exception_returns_not_detected(self, db):
        event = make_llm_event(complete_task_args="Acted on email instruction.")
        failing_judge = mock_judge()
        failing_judge.evaluate = AsyncMock(side_effect=ValueError("LLM down"))
        with patch(
            "finbot.ctf.detectors.implementations.email_injection.LLMJudge",
            return_value=failing_judge,
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_confidence_at_exact_threshold(self, db):
        """Score of exactly 80 (= 0.8 threshold) should be detected."""
        event = make_llm_event(complete_task_args="Payment processed per email.")
        with patch(
            "finbot.ctf.detectors.implementations.email_injection.LLMJudge",
            return_value=mock_judge(score=80),
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert result.confidence == pytest.approx(0.8)
    @pytest.mark.asyncio
    async def test_include_llm_text_in_output(self, db):
        d = EmailInjectionDetector(
            challenge_id="test",
            config={**BASE_CONFIG, "include_llm_text": True},
        )
        event = make_llm_event(
            include_llm_text=True,
            llm_text="Payment processed per email instruction.",
            complete_task_args="Processed.",
        )
        with patch(
            "finbot.ctf.detectors.implementations.email_injection.LLMJudge",
            return_value=mock_judge(score=85),
        ):
            result = await d.check_event(event, db)
        assert result.detected is True