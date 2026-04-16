"""OpenAI-compatible LLM client.

Supports both the OpenAI Responses API (when LLM_PROVIDER=openai and no
OPENAI_BASE_URL override) and the Chat Completions API used by Ollama and
other OpenAI-compatible backends.
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from finbot.config import settings
from finbot.core.data.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


def _normalize_messages(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert Responses API / mixed message formats to Chat Completions format.

    Handles:
    - ``type: function_call``        → assistant message with tool_calls
    - ``type: function_call_output`` → tool message with tool_call_id
    - ``role: developer``            → system message
    - Already-normalised assistant messages with tool_calls pass through intact.
    """
    out = []
    for m in raw:
        if not isinstance(m, dict):
            out.append(m)
            continue
        msg_type = m.get("type")
        role = m.get("role", "")

        if msg_type == "function_call":
            out.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": m.get("call_id", ""),
                    "type": "function",
                    "function": {
                        "name": m.get("name", ""),
                        "arguments": m.get("arguments", "{}"),
                    },
                }],
            })
            continue

        if msg_type == "function_call_output":
            out.append({
                "role": "tool",
                "tool_call_id": m.get("call_id", ""),
                "content": m.get("output", ""),
            })
            continue

        if role == "developer":
            out.append({"role": "system", "content": m.get("content", "")})
            continue

        if role in ("system", "user", "assistant", "tool"):
            if role == "assistant" and m.get("tool_calls"):
                out.append(m)  # already in Chat Completions format
            elif role == "tool" and "tool_call_id" in m:
                out.append(m)  # already in Chat Completions format
            else:
                out.append({"role": role, "content": m.get("content", "")})

    return out


def _normalize_tools(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Ensure tools are in Chat Completions ``{"type": "function", "function": {...}}`` format."""
    if not tools:
        return None
    out = []
    for t in tools:
        if not isinstance(t, dict):
            continue
        if t.get("type") == "function" and "function" in t:
            out.append(t)  # already wrapped
        elif "name" in t:
            out.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {}),
                },
            })
    return out or None


class OpenAIClient:
    """OpenAI-compatible client.

    Uses Chat Completions (``chat.completions.create``) so that it works with
    both OpenAI and Ollama/other compatible backends.
    """

    def __init__(self):
        self.default_model = settings.LLM_DEFAULT_MODEL
        self.default_temperature = settings.LLM_DEFAULT_TEMPERATURE
        self._client = self._get_client()

    def _get_client(self) -> AsyncOpenAI:
        import os

        # Precedence: explicit OPENAI_BASE_URL env var → ollama provider default → None (OpenAI)
        base_url = os.environ.get("OPENAI_BASE_URL") or (
            settings.OLLAMA_BASE_URL.rstrip("/") + "/v1"
            if settings.LLM_PROVIDER == "ollama"
            else None
        )
        return AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY or "ollama",
            base_url=base_url,
        )

    async def chat(self, request: LLMRequest) -> LLMResponse:
        try:
            model = request.model or self.default_model
            temperature = (
                self.default_temperature
                if request.temperature is None
                else request.temperature
            )

            messages = _normalize_messages(
                list(request.messages) if request.messages else []
            )
            tools = _normalize_tools(request.tools)

            params: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "max_tokens": settings.LLM_MAX_TOKENS,
                "timeout": settings.LLM_TIMEOUT,
                "temperature": temperature,
            }
            if tools:
                params["tools"] = tools
                params["tool_choice"] = "auto"

            response = await self._client.chat.completions.create(**params)

            if not response or not response.choices:
                return LLMResponse(
                    content="",
                    provider="openai",
                    success=False,
                    messages=messages,
                    tool_calls=[],
                )

            msg = response.choices[0].message
            content = msg.content or ""
            tool_calls: list[dict[str, Any]] = []
            new_messages = messages + [{"role": "assistant", "content": content}]

            if msg.tool_calls:
                tc_list = []
                for tc in msg.tool_calls:
                    parsed = json.loads(tc.function.arguments or "{}")
                    tool_calls.append({
                        "name": tc.function.name,
                        "call_id": tc.id,
                        "arguments": parsed,
                    })
                    tc_list.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })
                new_messages[-1] = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tc_list,
                }

            return LLMResponse(
                content=content,
                provider="openai",
                success=True,
                metadata={"response_id": response.id},
                messages=new_messages,
                tool_calls=tool_calls,
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("OpenAI chat failed: %s", e)
            raise Exception(f"OpenAI chat failed: {e}") from e  # pylint: disable=broad-exception-raised
