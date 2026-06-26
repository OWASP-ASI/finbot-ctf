"""Integration tests for before_final_action guardrail hooks."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finbot.agents.base import BaseAgent
from finbot.agents.chat import ChatAssistantBase
from finbot.core.auth.session import session_manager
from finbot.guardrails.schemas import HookKind


class _StubAgent(BaseAgent):
    """Minimal concrete agent for testing BaseAgent guardrail hooks."""

    def __init__(self, session_context, workflow_id: str = "wf_stub"):
        super().__init__(
            session_context=session_context,
            agent_name="stub_agent",
            workflow_id=workflow_id,
        )
        self.on_task_completion_called = False

    def _load_config(self) -> dict:
        return {}

    def _get_system_prompt(self) -> str:
        return "system prompt"

    async def _get_user_prompt(self, task_data: dict[str, Any] | None = None) -> str:
        return "user task"

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        return []

    def _get_callables(self) -> dict[str, Any]:
        return {}

    async def process(self, task_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        return {}

    async def _on_task_completion(self, task_result: dict[str, Any]) -> None:
        self.on_task_completion_called = True


class _StubChatAssistant(ChatAssistantBase):
    """Minimal chat assistant for testing final-response guardrail hook."""

    def _get_system_prompt(self) -> str:
        return "test prompt"

    def _get_native_tool_definitions(self) -> list[dict]:
        return []

    def _build_native_callables(self) -> dict[str, Any]:
        return {}


class TestCompleteTaskFinalActionHook:
    @pytest.fixture(autouse=True)
    def _setup(self, db):
        self.session = session_manager.create_session(
            email="final_action_base@example.com"
        )
        self.agent = _StubAgent(self.session)

    @pytest.mark.asyncio
    async def test_invoke_before_final_action_guardrail_payload(self):
        mock_invoke = AsyncMock(return_value=MagicMock())
        self.agent._guardrail_service.invoke = mock_invoke

        await self.agent._invoke_before_final_action_guardrail(
            task_status="success",
            task_summary="Invoice approved",
            tool_arguments={
                "task_status": "success",
                "task_summary": "Invoice approved",
            },
            tool_source="native",
        )

        mock_invoke.assert_called_once_with(
            HookKind.before_final_action,
            agent_name="stub_agent",
            task_status="success",
            task_summary="Invoice approved",
            tool_name="complete_task",
            tool_source="native",
            tool_arguments={
                "task_status": "success",
                "task_summary": "Invoice approved",
            },
        )

    @pytest.mark.asyncio
    async def test_complete_task_does_not_invoke_guardrail_directly(self):
        mock_invoke = AsyncMock(return_value=MagicMock())
        self.agent._guardrail_service.invoke = mock_invoke

        result = await self.agent._complete_task("success", "All done")

        assert result == {"task_status": "success", "task_summary": "All done"}
        assert self.agent.on_task_completion_called is True
        mock_invoke.assert_not_called()

    @pytest.mark.asyncio
    @patch("finbot.agents.base.event_bus")
    async def test_complete_task_tool_loop_guardrail_sequence(self, mock_bus):
        mock_bus.emit_agent_event = AsyncMock()

        from finbot.core.data.models import LLMResponse

        mock_llm_response = LLMResponse(
            content=None,
            tool_calls=[
                {
                    "name": "complete_task",
                    "call_id": "call_complete",
                    "arguments": {
                        "task_status": "success",
                        "task_summary": "done",
                    },
                }
            ],
            messages=[],
        )

        mock_invoke = AsyncMock(return_value=MagicMock())
        self.agent._guardrail_service.invoke = mock_invoke
        self.agent.llm_client.chat = AsyncMock(return_value=mock_llm_response)
        self.agent._connect_mcp_servers = AsyncMock()
        self.agent.log_task_completion = AsyncMock()

        await self.agent._run_agent_loop(task_data={})

        hook_kinds = [call.args[0] for call in mock_invoke.call_args_list]
        assert hook_kinds == [HookKind.before_final_action, HookKind.after_tool]
        assert HookKind.before_tool not in hook_kinds

        before_final = mock_invoke.call_args_list[0].kwargs
        assert before_final["task_status"] == "success"
        assert before_final["task_summary"] == "done"
        assert before_final["tool_name"] == "complete_task"

        after_tool = mock_invoke.call_args_list[1].kwargs
        assert after_tool["tool_name"] == "complete_task"
        assert after_tool["tool_result"] == str(
            {"task_status": "success", "task_summary": "done"}
        )

    @pytest.mark.asyncio
    @patch("finbot.agents.base.event_bus")
    async def test_forced_complete_task_invokes_guardrail_before_execution(
        self, mock_bus
    ):
        mock_bus.emit_agent_event = AsyncMock()

        mock_helper = AsyncMock()
        self.agent._invoke_before_final_action_guardrail = mock_helper
        self.agent._connect_mcp_servers = AsyncMock()
        self.agent.log_task_completion = AsyncMock()
        self.agent.llm_client.chat = AsyncMock(
            side_effect=RuntimeError("iteration failed")
        )

        await self.agent._run_agent_loop(task_data={})

        mock_helper.assert_called_once()
        assert mock_helper.call_args.kwargs["task_status"] == "failed"
        assert "iteration failed" in mock_helper.call_args.kwargs["task_summary"]


class TestChatFinalActionHook:
    @pytest.fixture(autouse=True)
    def _setup(self, db):
        self.session = session_manager.create_session(
            email="final_action_chat@example.com"
        )
        self.assistant = _StubChatAssistant(self.session)

    @pytest.mark.asyncio
    async def test_invoke_before_final_action_guardrail_payload(self):
        mock_invoke = AsyncMock(return_value=MagicMock())
        self.assistant._guardrail_service.invoke = mock_invoke

        await self.assistant._invoke_before_final_action_guardrail(
            response_content="Hello vendor",
            user_message="What is my status?",
            duration_ms=1200,
        )

        mock_invoke.assert_called_once_with(
            HookKind.before_final_action,
            agent_name="chat_assistant",
            user_message="What is my status?",
            model_output="Hello vendor",
            model=self.assistant._model,
            tool_name="chat_response",
            tool_source="native",
            tool_arguments={
                "response_content": "Hello vendor",
                "user_message": "What is my status?",
                "duration_ms": 1200,
            },
        )

    @pytest.mark.asyncio
    async def test_stream_response_invokes_hook_before_save(self):
        mock_helper = AsyncMock()
        self.assistant._invoke_before_final_action_guardrail = mock_helper
        self.assistant._connect_mcp = AsyncMock()
        self.assistant._save_message = MagicMock()
        self.assistant._load_history = MagicMock(return_value=[])

        class DeltaEvent:
            type = "response.output_text.delta"

            def __init__(self, text: str):
                self.delta = text

        class FakeStream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if not hasattr(self, "_sent"):
                    self._sent = True
                    return DeltaEvent("Hello vendor")
                raise StopAsyncIteration

        with patch("finbot.agents.chat.event_bus") as mock_bus:
            mock_bus.emit_agent_event = AsyncMock()
            self.assistant._client.responses.create = AsyncMock(
                return_value=FakeStream()
            )

            chunks = []
            async for chunk in self.assistant.stream_response("What is my status?"):
                chunks.append(chunk)

        mock_helper.assert_called_once_with(
            response_content="Hello vendor",
            user_message="What is my status?",
            duration_ms=mock_helper.call_args.kwargs["duration_ms"],
        )
        self.assistant._save_message.assert_any_call("user", "What is my status?")
        self.assistant._save_message.assert_any_call("assistant", "Hello vendor")
        assert any("done" in chunk for chunk in chunks)

    @pytest.mark.asyncio
    async def test_hook_runs_before_save_message(self):
        events: list[tuple[str, str | None]] = []

        async def track_helper(**_kwargs):
            events.append(("guardrail", None))

        def track_save(role, content, workflow_id=None):
            events.append(("save", role))

        self.assistant._invoke_before_final_action_guardrail = track_helper
        self.assistant._connect_mcp = AsyncMock()
        self.assistant._save_message = track_save
        self.assistant._load_history = MagicMock(return_value=[])

        class DeltaEvent:
            type = "response.output_text.delta"

            def __init__(self, text: str):
                self.delta = text

        class FakeStream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if not hasattr(self, "_sent"):
                    self._sent = True
                    return DeltaEvent("Reply text")
                raise StopAsyncIteration

        with patch("finbot.agents.chat.event_bus") as mock_bus:
            mock_bus.emit_agent_event = AsyncMock()
            self.assistant._client.responses.create = AsyncMock(
                return_value=FakeStream()
            )

            async for _ in self.assistant.stream_response("Hi"):
                pass

        assert events == [
            ("save", "user"),
            ("guardrail", None),
            ("save", "assistant"),
        ]
