# Tests for OrchestratorAgent.delegate_to_payments's next_step instruction.
#
# Bug (GitHub issue #460): next_step was appended unconditionally, regardless
# of whether the Payments Agent actually succeeded. A failed payment
# (task_status="failed") still told the orchestrator's own LLM "you MUST now
# notify the vendor... use notification_type payment_confirmation" -- actively
# instructing it to tell the vendor a payment succeeded when it didn't.
#
# Note on the fix: the issue's own suggested patch checked
# `task_status == "completed"`. That value does not exist in this codebase --
# verified against finbot/agents/base.py:373-376, where the complete_task
# tool schema declares `"enum": ["success", "failed"]`. "completed" is never
# a valid task_status anywhere in the agent framework. Checking for it would
# make next_step never fire, even on genuine success, silently breaking the
# legitimate vendor-notification handoff. The correct guard is
# `task_status == "success"`.

import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from finbot.agents.orchestrator import OrchestratorAgent
from finbot.core.auth.session import SessionContext


def _make_session_context() -> SessionContext:
    created_at = datetime.now(UTC)
    return SessionContext(
        session_id="sess_test",
        user_id="user_test",
        is_temporary=False,
        namespace="ns_test",
        created_at=created_at,
        expires_at=created_at + timedelta(hours=24),
    )


class TestDelegateToPaymentsNextStep:

    @pytest.fixture(autouse=True)
    def mock_event_bus(self):
        """Mock the event bus to prevent real Redis connections in unit tests."""
        with patch("finbot.agents.base.event_bus") as mock_bus, \
             patch("finbot.agents.orchestrator.event_bus", mock_bus), \
             patch("finbot.agents.utils.event_bus", mock_bus), \
             patch("finbot.core.llm.contextual_client.event_bus", mock_bus):
            mock_bus.emit_agent_event = AsyncMock()
            mock_bus.emit_business_event = AsyncMock()
            yield mock_bus

    def _make_orchestrator(self) -> OrchestratorAgent:
        return OrchestratorAgent(session_context=_make_session_context(), workflow_id="wf_test")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sets_next_step_on_success(self):
        agent = self._make_orchestrator()
        payments_result = {"task_status": "success", "task_summary": "Paid $500 via wire."}

        with patch(
            "finbot.agents.runner.run_payments_agent",
            new_callable=AsyncMock,
            return_value=payments_result,
        ):
            result = await agent.delegate_to_payments(invoice_id=1, task_description="Pay")

        assert "next_step" in result
        assert "payment_confirmation" in result["next_step"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_omits_next_step_on_failure(self):
        agent = self._make_orchestrator()
        payments_result = {
            "task_status": "failed",
            "task_summary": "Payment declined -- insufficient funds.",
        }

        with patch(
            "finbot.agents.runner.run_payments_agent",
            new_callable=AsyncMock,
            return_value=payments_result,
        ):
            result = await agent.delegate_to_payments(invoice_id=1, task_description="Pay")

        assert "next_step" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_omits_next_step_when_status_missing(self):
        """Defensive: if the Payments Agent ever returns a result dict
        without task_status at all, must not default to notifying the
        vendor of a payment that was never confirmed."""
        agent = self._make_orchestrator()
        payments_result = {"task_summary": "Something happened."}

        with patch(
            "finbot.agents.runner.run_payments_agent",
            new_callable=AsyncMock,
            return_value=payments_result,
        ):
            result = await agent.delegate_to_payments(invoice_id=1, task_description="Pay")

        assert "next_step" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_omits_next_step_when_delegation_cap_reached(self):
        """When the delegation cap is hit, delegate_to_payments returns the
        cap_result directly without ever calling run_payments_agent -- must
        not carry a next_step instruction either."""
        agent = self._make_orchestrator()
        agent._delegation_attempts["payments"] = agent._max_delegation_attempts

        with patch(
            "finbot.agents.runner.run_payments_agent",
            new_callable=AsyncMock,
        ) as mock_run:
            result = await agent.delegate_to_payments(invoice_id=1, task_description="Pay")

        mock_run.assert_not_called()
        assert "next_step" not in result
        assert result["task_status"] == "failed"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_omits_next_step_on_unrecognized_status(self):
        """Defensive against schema drift: an unexpected task_status value
        must not be treated as success."""
        agent = self._make_orchestrator()
        payments_result = {"task_status": "completed", "task_summary": "Paid."}

        with patch(
            "finbot.agents.runner.run_payments_agent",
            new_callable=AsyncMock,
            return_value=payments_result,
        ):
            result = await agent.delegate_to_payments(invoice_id=1, task_description="Pay")

        assert "next_step" not in result
