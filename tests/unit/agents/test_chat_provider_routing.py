from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from finbot.agents import chat as chat_module
from finbot.agents.chat import ChatAssistantBase
from finbot.core.auth.session import SessionContext
from finbot.core.data.models import LLMResponse


class DummyChatAssistant(ChatAssistantBase):
    def _resolve_workflow_id(self) -> str:
        return "wf_test_chat"

    async def _connect_mcp(self) -> None:
        self._mcp_connected = True

    def _get_system_prompt(self) -> str:
        return "You are a test assistant."

    def _get_native_tool_definitions(self) -> list[dict]:
        return []

    def _build_native_callables(self) -> dict:
        return {}

    def _load_history(self) -> list[dict]:
        return []

    def _save_message(self, role: str, content: str, workflow_id: str | None = None):
        return None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_chat_assistant_uses_llm_router_for_non_openai_provider(monkeypatch):
    fake_llm_client = SimpleNamespace(
        default_model="gemma4:e2b",
        chat=AsyncMock(
            return_value=LLMResponse(
                content="local response",
                provider="ollama",
                success=True,
                messages=[{"role": "assistant", "content": "local response"}],
                tool_calls=[],
            )
        ),
    )

    monkeypatch.setattr(chat_module.settings, "LLM_PROVIDER", "ollama")
    monkeypatch.setattr(chat_module.settings, "OLLAMA_MODEL", "gemma4:e2b")
    monkeypatch.setattr(chat_module, "get_llm_client", lambda: fake_llm_client)
    monkeypatch.setattr(chat_module.event_bus, "emit_agent_event", AsyncMock())

    session_context = SessionContext(
        session_id="session_test",
        user_id="user_test",
        is_temporary=True,
        namespace="test",
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        current_vendor_id=1,
    )
    assistant = DummyChatAssistant(session_context=session_context)
    assistant._guardrail_service.invoke = AsyncMock()

    chunks = [chunk async for chunk in assistant.stream_response("hello")]

    assert assistant._client is None
    fake_llm_client.chat.assert_awaited_once()
    assert fake_llm_client.chat.await_args.kwargs["request"].model == "gemma4:e2b"
    assert any('"content": "local response"' in chunk for chunk in chunks)
    assert chunks[-1] == 'data: {"type": "done"}\n\n'
