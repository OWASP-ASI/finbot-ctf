"""Shared fixtures for detector unit tests."""

import pytest
from unittest.mock import AsyncMock, MagicMock


def make_llm_event(
    agent_name="onboarding_agent",
    system_prompt="You are a helpful agent.",
    complete_task_args="Vendor approved after normal review.",
    include_llm_text=False,
    llm_text="",
):
    """Build a realistic agent.*.llm_request_success event."""
    tool_calls = [{"name": "complete_task", "arguments": complete_task_args}]
    if include_llm_text:
        response_dump = {"content": llm_text, "tool_calls": tool_calls}
    else:
        response_dump = {"content": None, "tool_calls": tool_calls}

    return {
        "event_type": f"agent.{agent_name}.llm_request_success",
        "namespace": "test-ns",
        "user_id": "user-1",
        "request_dump": {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Process this vendor."},
            ]
        },
        "response_dump": response_dump,
    }


def mock_judge(score=90, reasoning="Attack detected."):
    """Return an AsyncMock LLMJudge whose evaluate() returns a verdict."""
    verdict = MagicMock()
    verdict.score = score
    verdict.reasoning = reasoning

    judge = MagicMock()
    judge.evaluate = AsyncMock(return_value=verdict)
    return judge


@pytest.fixture
def high_confidence_judge():
    """Judge that always returns score=90 (detected at default 0.8 threshold)."""
    return mock_judge(score=90, reasoning="Clear impersonation detected.")


@pytest.fixture
def low_confidence_judge():
    """Judge that always returns score=30 (not detected)."""
    return mock_judge(score=30, reasoning="No attack found.")