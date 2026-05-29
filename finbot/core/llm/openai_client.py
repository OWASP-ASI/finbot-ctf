"""OpenAI Client with configurable model

TODO: for reasoning capabilities, we need to use Responses API

"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from finbot.config import settings
from finbot.core.data.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIClient:
    """OpenAI Client with configurable model"""

    def __init__(self):
        self.default_model = settings.LLM_DEFAULT_MODEL
        self.default_temperature = settings.LLM_DEFAULT_TEMPERATURE
        self._client = self._get_client()

    def _get_client(self):
        """Get the OpenAI client"""
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def chat(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """
        Chat with OpenAI
        """
        try:
            model = request.model or self.default_model
            temperature = (
                self.default_temperature if request.temperature is None else request.temperature
            )
            max_tokens = settings.LLM_MAX_TOKENS

            input_list: list[dict[str, Any]] = list(request.messages) if request.messages else []

            tool_calls: list[dict[str, Any]] = []

            create_params = {
                "model": model,
                "input": input_list,
                "max_output_tokens": max_tokens,
                "timeout": settings.LLM_TIMEOUT,
            }

            no_temperature = any(model.startswith(p) for p in ("o1", "o3", "o4", "gpt-5"))
            if not no_temperature:
                create_params["temperature"] = temperature

            if request.output_json_schema:
                create_params["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": request.output_json_schema["name"],
                        "schema": request.output_json_schema["schema"],
                        "strict": True,
                    }
                }

            if request.tools:
                create_params["tools"] = request.tools

            if request.previous_response_id:
                create_params["previous_response_id"] = request.previous_response_id

            response = await self._client.responses.create(**create_params)

            # Guard against malformed or empty SDK responses.
            # Prevents AttributeError when accessing response.message.content
            # and ensures consistent failure handling.
            if not response:
                logger.warning("Invalid OpenAI response: response is None")
                return LLMResponse(
                    content="",
                    provider="openai",
                    success=False,
                    messages=input_list,
                    tool_calls=[],
                )

            output = response.output if isinstance(response.output, list) else []
            if not isinstance(response.output, list) and response.output:
                logger.warning(
                    "Unexpected response.output type from OpenAI: %s — ignoring",
                    type(response.output),
                )

            new_entries: list[dict[str, Any]] = []

            # Extract tool calls and messages for future calls
            # (TODO): take care of refusals
            for item in output:

                if item.type == "message":
                    texts = []

                    for content in item.content:
                        # Handle content whether it arrives as a raw dictionary
                        # or an SDK object (TypedDict vs Pydantic)
                        content_type = (
                            content.get("type")
                            if isinstance(content, dict)
                            else getattr(content, "type", None)
                        )
                        content_text = (
                            content.get("text")
                            if isinstance(content, dict)
                            else getattr(content, "text", None)
                        )

                        if content_type == "output_text" and content_text:
                            texts.append(content_text)

                    new_entries.append(
                        {
                            "role": item.role,
                            "content": "".join(texts),
                        }
                    )
                elif item.type == "function_call":
                    # Safe JSON parsing (avoid crash if malformed)
                    raw_args = item.arguments
                    parsed_args = json.loads(raw_args)

                    tool_call = {
                        "name": item.name,
                        "call_id": item.call_id,
                        "arguments": parsed_args,
                    }
                    tool_calls.append(tool_call)
                    # Add the function call to the conversation history
                    new_entries.append(
                        {
                            "type": "function_call",
                            "name": item.name,
                            "call_id": item.call_id,
                            "arguments": raw_args,
                        }
                    )

            input_list = input_list + new_entries

            metadata = {
                "response_id": response.id,
            }

            return LLMResponse(
                content=response.output_text,
                provider="openai",
                success=True,
                metadata=metadata,
                messages=input_list,
                tool_calls=tool_calls,
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("OpenAI chat failed: %s", e)
            raise Exception(
                f"OpenAI chat failed: {e}"
            ) from e  # pylint: disable=broad-exception-raised
