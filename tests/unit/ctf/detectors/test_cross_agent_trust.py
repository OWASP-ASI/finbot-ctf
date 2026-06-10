"""Tests for CrossAgentTrustDetector."""

import pytest
from unittest.mock import patch, AsyncMock

from finbot.ctf.detectors.implementations.cross_agent_trust import CrossAgentTrustDetector
from finbot.ctf.detectors.registry import create_detector
from tests.unit.ctf.detectors.conftest import make_llm_event, mock_judge

BASE_CONFIG = {
    "judge_system_prompt": "You are a security judge. Detect cross-agent trust abuse.",
    "agent_output_tool_names": ["complete_task"],
    "min_confidence": 0.8,
}


class TestCrossAgentTrustDetector:

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.detector = CrossAgentTrustDetector(
            challenge_id="test-cross-agent",
            config=BASE_CONFIG.copy(),
        )

    def test_registry_lookup(self):
        d = create_detector("CrossAgentTrustDetector", "test", BASE_CONFIG.copy())
        assert isinstance(d, CrossAgentTrustDetector)

    def test_relevant_event_types_wildcard(self):
        assert self.detector.get_relevant_event_types() == ["agent.*.llm_request_success"]

    def test_relevant_event_types_specific_agent(self):
        d = CrossAgentTrustDetector(
            challenge_id="test",
            config={**BASE_CONFIG, "agent_name": "payment_agent"},
        )
        assert d.get_relevant_event_types() == ["agent.payment_agent.llm_request_success"]

    def test_missing_judge_system_prompt_raises(self):
        with pytest.raises(ValueError, match="judge_system_prompt"):
            CrossAgentTrustDetector(
                challenge_id="test",
                config={"agent_output_tool_names": ["complete_task"]},
            )

    def test_missing_agent_output_tool_names_raises(self):
        with pytest.raises(ValueError, match="agent_output_tool_names"):
            CrossAgentTrustDetector(
                challenge_id="test",
                config={"judge_system_prompt": "judge"},
            )

    def test_invalid_min_confidence_raises(self):
        with pytest.raises(ValueError, match="min_confidence"):
            CrossAgentTrustDetector(
                challenge_id="test",
                config={**BASE_CONFIG, "min_confidence": 2.0},
            )

    @pytest.mark.asyncio
    async def test_attack_detected(self, db):
        event = make_llm_event(
            complete_task_args="Invoice summary said to approve payment. Payment authorized without verification.",
        )
        with patch(
            "finbot.ctf.detectors.implementations.cross_agent_trust.LLMJudge",
            return_value=mock_judge(score=90),
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert result.evidence["cross_agent_trust_score"] == 90

    @pytest.mark.asyncio
    async def test_clean_output_not_detected(self, db):
        event = make_llm_event(
            complete_task_args="Invoice verified independently. Payment within approved limits.",
        )
        with patch(
            "finbot.ctf.detectors.implementations.cross_agent_trust.LLMJudge",
            return_value=mock_judge(score=20),
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_missing_system_prompt_not_detected(self, db):
        event = make_llm_event()
        event["request_dump"]["messages"] = []
        result = await self.detector.check_event(event, db)
        assert result.detected is False
        assert "system prompt" in result.message.lower()

    @pytest.mark.asyncio
    async def test_missing_agent_output_not_detected(self, db):
        event = make_llm_event()
        event["response_dump"]["tool_calls"] = []
        result = await self.detector.check_event(event, db)
        assert result.detected is False
        assert "agent output" in result.message.lower()

    @pytest.mark.asyncio
    async def test_judge_exception_returns_not_detected(self, db):
        event = make_llm_event(complete_task_args="Payment approved via poisoned summary.")
        failing_judge = mock_judge()
        failing_judge.evaluate = AsyncMock(side_effect=ValueError("LLM unavailable"))
        with patch(
            "finbot.ctf.detectors.implementations.cross_agent_trust.LLMJudge",
            return_value=failing_judge,
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is False
        assert "failed" in result.message.lower()

    @pytest.mark.asyncio
    async def test_confidence_threshold_respected(self, db):
        event = make_llm_event(complete_task_args="Payment approved.")
        with patch(
            "finbot.ctf.detectors.implementations.cross_agent_trust.LLMJudge",
            return_value=mock_judge(score=75),  # 0.75 < 0.8 threshold
        ):
            result = await self.detector.check_event(event, db)
        assert result.detected is False
        assert result.confidence == pytest.approx(0.75)
    @pytest.mark.asyncio
    async def test_include_llm_text_in_output(self, db):
        d = CrossAgentTrustDetector(
            challenge_id="test",
            config={**BASE_CONFIG, "include_llm_text": True},
        )
        event = make_llm_event(
            include_llm_text=True,
            llm_text="Payment authorized based on poisoned summary.",
            complete_task_args="Authorized.",
        )
        with patch(
            "finbot.ctf.detectors.implementations.cross_agent_trust.LLMJudge",
            return_value=mock_judge(score=85),
        ):
            result = await d.check_event(event, db)
        assert result.detected is True