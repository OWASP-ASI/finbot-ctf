"""Ollama Client with configurable model"""

import logging
from typing import Any

from ollama import AsyncClient

from finbot.config import settings
from finbot.core.data.models import LLMRequest, LLMResponse
from finbot.core.llm.utils import retry

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama Client with configurable model"""

    def __init__(self):
        self.default_model = settings.LLM_DEFAULT_MODEL
        self.default_temperature = settings.LLM_DEFAULT_TEMPERATURE
        self.host = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")

        self._client = AsyncClient(
            host=self.host,
            timeout=settings.LLM_TIMEOUT,
        )

    @retry(max_retries=3, backoff_seconds=0.5)
    async def chat(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """
        Chat with Ollama
        """
        try:
            model = request.model or self.default_model
            temperature = (
                self.default_temperature if request.temperature is None else request.temperature
            )

            # Create a shallow copy to avoid mutating request.messages.
            # Prevents history leakage when the same LLMRequest object is reused.
            messages: list[dict[str, Any]] = list(request.messages) if request.messages else []

            options = {
                "temperature": temperature,
                "num_predict": settings.LLM_MAX_TOKENS,
            }

            chat_params = {
                "model": model,
                "messages": messages,
                "options": options,
            }

            if request.output_json_schema:
                chat_params["format"] = request.output_json_schema.get("schema")

            if request.tools:
                chat_params["tools"] = request.tools

            response = await self._client.chat(**chat_params)

            # Guard against invalid SDK responses.
            # Prevents AttributeError and centralizes response validation.
            if not response or not getattr(response, "message", None):
                logger.warning("Invalid Ollama response: message is None")
                return LLMResponse(
                    content="",
                    provider="ollama",
                    success=False,
                    messages=messages,
                    tool_calls=[],
                )

            message = response.message

            # Normalize content to str
            content = message.content if isinstance(message.content, str) else ""

            tool_calls: list[dict[str, Any]] = []
            raw_tool_calls = getattr(message, "tool_calls", [])
            if isinstance(raw_tool_calls, list) and raw_tool_calls:
                for idx, tc in enumerate(raw_tool_calls):
                    function = getattr(tc, "function", None)
                    tool_calls.append(
                        {
                            "name": getattr(function, "name", None),
                            "call_id": f"ollama_call_{idx}",
                            "arguments": getattr(function, "arguments", None),
                        }
                    )
            elif raw_tool_calls:
                logger.warning(
                    "Unexpected tool_calls type from Ollama: %s — ignoring",
                    type(raw_tool_calls),
                )

            # tool_calls normalized to plain dicts — JSON-serializable
            history_entry: dict[str, Any] = {
                "role": "assistant",
                "content": content,
            }
            if tool_calls:
                history_entry["tool_calls"] = tool_calls

            messages = messages + [history_entry]

            metadata = {
                "total_duration": getattr(response, "total_duration", None),
                "load_duration": getattr(response, "load_duration", None),
                "eval_count": getattr(response, "eval_count", None),
            }

            return LLMResponse(
                content=content,
                provider="ollama",
                success=True,
                metadata=metadata,
                messages=messages,
                tool_calls=tool_calls,
            )

        except Exception as e:
            logger.error("Ollama chat failed: %s", e)
            raise
