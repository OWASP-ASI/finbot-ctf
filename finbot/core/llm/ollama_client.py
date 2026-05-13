"""Ollama Client with configurable model"""

import asyncio
import json
import logging
from typing import Any

from ollama import AsyncClient
from finbot.core.llm.utils import retry
from finbot.config import settings
from finbot.core.data.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama Client with configurable model"""

    def __init__(self):
        raw_provider = getattr(settings, "LLM_PROVIDER", "openai")
        self.provider = (
            raw_provider.strip().lower() if isinstance(raw_provider, str) else "openai"
        )
        self.default_model = (
            settings.OLLAMA_MODEL if self.provider == "ollama" else settings.LLM_DEFAULT_MODEL
        )
        self.default_temperature = settings.LLM_DEFAULT_TEMPERATURE
        self.host = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self._default_model_checked = False
        self._default_model_lock = asyncio.Lock()

        self._client = AsyncClient(
            host=self.host,
            timeout=settings.LLM_TIMEOUT,
        )

    @staticmethod
    def _extract_model_name(model: Any) -> str | None:
        if isinstance(model, dict):
            return model.get("model") or model.get("name")
        return getattr(model, "model", None) or getattr(model, "name", None)

    @classmethod
    def _model_is_available(
        cls, requested_model: str, available_models: list[Any]
    ) -> bool:
        requested = requested_model.strip()
        if not requested:
            return False

        requested_with_latest = f"{requested}:latest" if ":" not in requested else requested
        for model in available_models:
            model_name = cls._extract_model_name(model)
            if model_name in {requested, requested_with_latest}:
                return True
        return False

    async def _ensure_default_model_available(self) -> None:
        if self.provider != "ollama" or self._default_model_checked:
            return

        async with self._default_model_lock:
            if self._default_model_checked:
                return

            models_response = await self._client.list()
            available_models = list(getattr(models_response, "models", []) or [])
            if not self._model_is_available(self.default_model, available_models):
                logger.info(
                    "Ollama model %s is not installed; pulling it now",
                    self.default_model,
                )
                await self._client.pull(self.default_model)

            self._default_model_checked = True

    @staticmethod
    def _coerce_tool_arguments(arguments: Any) -> dict[str, Any]:
        """Convert provider-neutral tool arguments into Ollama's mapping shape."""
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @classmethod
    def _normalize_messages(cls, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert internal/OpenAI-style tool history into Ollama chat messages."""
        normalized: list[dict[str, Any]] = []
        tool_call_names: dict[str, str] = {}

        for message in messages:
            msg = dict(message)
            msg_type = msg.get("type")

            if msg_type == "function_call":
                name = msg.get("name")
                call_id = msg.get("call_id")
                if call_id and name:
                    tool_call_names[call_id] = name
                if name:
                    normalized.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": name,
                                        "arguments": cls._coerce_tool_arguments(
                                            msg.get("arguments")
                                        ),
                                    }
                                }
                            ],
                        }
                    )
                continue

            if msg_type == "function_call_output":
                call_id = msg.get("call_id")
                tool_name = tool_call_names.get(call_id, call_id or "tool")
                normalized.append(
                    {
                        "role": "tool",
                        "content": str(msg.get("output") or ""),
                        "tool_name": tool_name,
                    }
                )
                continue

            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list):
                ollama_tool_calls: list[dict[str, Any]] = []
                for tool_call in tool_calls:
                    function = tool_call.get("function", {})
                    name = tool_call.get("name") or function.get("name")
                    call_id = tool_call.get("call_id")
                    if call_id and name:
                        tool_call_names[call_id] = name
                    if name:
                        ollama_tool_calls.append(
                            {
                                "function": {
                                    "name": name,
                                    "arguments": cls._coerce_tool_arguments(
                                        tool_call.get(
                                            "arguments", function.get("arguments")
                                        )
                                    ),
                                }
                            }
                        )

                normalized_message = {
                    "role": msg.get("role", "assistant"),
                    "content": str(msg.get("content") or ""),
                }
                if ollama_tool_calls:
                    normalized_message["tool_calls"] = ollama_tool_calls
                normalized.append(normalized_message)
                continue

            normalized.append(
                {
                    key: value
                    for key, value in msg.items()
                    if key in {"role", "content", "images", "tool_name"}
                }
            )

        return normalized

    @staticmethod
    def _normalize_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Convert OpenAI Responses-style tool definitions into Ollama's format."""
        if not tools:
            return None

        normalized: list[dict[str, Any]] = []
        for tool in tools:
            if tool.get("type") == "function" and "function" not in tool:
                normalized.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.get("name"),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {}),
                        },
                    }
                )
            else:
                normalized.append(tool)
        return normalized

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
            if model == self.default_model:
                await self._ensure_default_model_available()

            # Create a shallow copy to avoid mutating request.messages.
            # Prevents history leakage when the same LLMRequest object is reused.
            messages = self._normalize_messages(list(request.messages or []))

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

            tools = self._normalize_tools(request.tools)
            if tools:
                chat_params["tools"] = tools

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
