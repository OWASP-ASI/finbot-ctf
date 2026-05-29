# ==============================================================================
# OpenAI Client Test Suite
# ==============================================================================
# User Story: As a developer, I want OpenAIClient to reliably communicate with
#             the OpenAI Responses API so that the platform can run cloud AI
#             inference with stateful conversation chaining.
#
# Acceptance Criteria:
#   1. Loads configuration from settings at instantiation
#   2. Sends correctly formatted requests and parses responses
#   3. Extracts tool calls and chains conversations via previous_response_id
#   4. Forwards temperature correctly, including zero (does not swap with default)
#   5. Does not mutate the caller's LLMRequest or message list
#   6. Handles malformed API responses without crashing
#
# Test Categories:
#   LLM-OAPI-001: Configuration Loading
#   LLM-OAPI-002: Successful Chat Completion
#   LLM-OAPI-003: JSON Schema Formatting
#   LLM-OAPI-004: Tool Calls Handling
#   LLM-OAPI-005: Previous Response ID Chaining
#   LLM-OAPI-006: Message History Preservation
#   LLM-OAPI-007: Zero Temperature Not Overridden
#   LLM-OAPI-008: Explicit Temperature Passed Through
#   LLM-OAPI-009: None Temperature Falls Back to Default
#   LLM-OAPI-ERR-001: Malformed JSON in Function Arguments
#   LLM-OAPI-ERR-002: API Network Error Handling
#   LLM-OAPI-EDGE-001: Empty Tool Calls List
#   LLM-OAPI-EDGE-002: Tool Calls With Unexpected Output Type
#   LLM-OAPI-EDGE-003: Tool Call Missing Required Fields
#   LLM-OAPI-EDGE-004: Request With Messages Set to None
#   LLM-OAPI-EDGE-005: Message Content With Unexpected Type
#   LLM-OAPI-EDGE-006: Unexpected Exception Not Retried
#   LLM-OAPI-EDGE-007: Messages List Not Mutated on Chat (bug documentation)
#   LLM-OAPI-EDGE-008: Response Messages Independent of Request Messages (bug documentation)
#   LLM-OAPI-EDGE-009: Second Call Does Not Inherit First Call History (bug documentation)
#   LLM-OAPI-GSI-001: Google Sheets Integration Verification
# ==============================================================================

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import gspread
import pytest
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from finbot.core.data.models import LLMRequest
from finbot.core.llm.openai_client import OpenAIClient

load_dotenv()

# ---- mock openai ----
mock_openai = MagicMock()
mock_openai.AsyncOpenAI = MagicMock()
sys.modules["openai"] = mock_openai
# --------------------------------------------------------------


@pytest.fixture
def mock_openai_settings():
    """Patch openai_client.settings with safe test defaults.

    Uses gpt-4o (not gpt-5-nano) — the no_temperature filter skips adding
    'temperature' for gpt-5/o1/o3/o4 model families, breaking tests 007-009.
    """
    with patch("finbot.core.llm.openai_client.settings") as ms:
        ms.LLM_DEFAULT_MODEL = "gpt-4o"
        ms.LLM_DEFAULT_TEMPERATURE = 0.7
        ms.OPENAI_API_KEY = "test-key"
        ms.LLM_MAX_TOKENS = 4096
        ms.LLM_TIMEOUT = 60
        yield ms


# ============================================================================
# LLM-OAPI-001: Configuration Loading
# ============================================================================
@pytest.mark.unit
def test_configuration_loading():
    """LLM-OAPI-001: Configuration Loading

    Verify that OpenAIClient loads configuration from settings correctly.

    Test Steps:
    1. Mock settings with:
       - LLM_DEFAULT_MODEL = "gpt-5-nano"
       - LLM_DEFAULT_TEMPERATURE = 0.7
       - OPENAI_API_KEY = "test-key"
    2. Mock AsyncOpenAI client
    3. Create OpenAIClient instance
    4. Verify default_model matches settings
    5. Verify default_temperature matches settings
    6. Verify AsyncOpenAI initialized with API key

    Expected Results:
    1. OpenAIClient instance created successfully
    2. default_model = "gpt-5-nano"
    3. default_temperature = 0.7
    4. AsyncOpenAI client configured with correct API key
    5. No initialization errors
    """
    with patch("finbot.core.llm.openai_client.settings") as mock_settings:
        mock_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
        mock_settings.LLM_DEFAULT_TEMPERATURE = 0.7
        mock_settings.OPENAI_API_KEY = "test-api-key"

        with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
            client = OpenAIClient()

            # The client must store the model name from settings — used as the default for every request
            assert client.default_model == "gpt-5-nano"
            # Temperature controls randomness; 0=fully deterministic, 1=very creative
            assert client.default_temperature == pytest.approx(0.7)
            # AsyncOpenAI must receive the API key from settings — without it every request will be rejected
            mock_async_openai.assert_called_once_with(api_key="test-api-key")


# ============================================================================
# LLM-OAPI-002: Successful Chat Completion
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_successful_chat_completion(mock_openai_settings):
    """LLM-OAPI-002: Successful Chat Completion

    Verify that OpenAIClient successfully processes chat requests.

    Test Steps:
    1. Create mock OpenAI response with:
       - response.id = "response_123"
       - response.output_text = "Hello from OpenAI"
       - response.output = [message_item]
       - message_item.type = "message"
       - message_item.content = [output_text_content]
    2. Mock AsyncOpenAI client to return fake response
    3. Create OpenAIClient instance
    4. Create LLMRequest with basic message
    5. Call client.chat(request)
    6. Verify response fields match expected values

    Expected Results:
    1. Chat request completes successfully
    2. Response content = "Hello from OpenAI"
    3. Response provider = "openai"
    4. Response success = True
    5. Response metadata contains response_id
    """
    # Create mock message content
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "Hello from OpenAI"

    # Create mock message item
    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    # Create mock response
    mock_response = MagicMock()
    mock_response.id = "response_123"
    mock_response.output_text = "Hello from OpenAI"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        request = LLMRequest(messages=[{"role": "user", "content": "Hi"}])

        response = await client.chat(request)

        # The call must complete without raising an exception
        assert response.success is True
        # The provider field tells the caller which backend produced this response
        assert response.provider == "openai"
        # The reply text from OpenAI must be passed through unchanged
        assert response.content == "Hello from OpenAI"
        # The response ID is saved so future requests can chain onto this conversation
        assert response.metadata is not None and response.metadata["response_id"] == "response_123"


# ============================================================================
# LLM-OAPI-003: JSON Schema Formatting
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_json_schema_formatting(mock_openai_settings):
    """LLM-OAPI-003: JSON Schema Formatting

    Verify that output_json_schema is properly formatted for OpenAI Responses API.

    Test Steps:
    1. Define JSON schema with name and schema fields
    2. Create mock OpenAI response
    3. Create LLMRequest with output_json_schema
    4. Call client.chat(request)
    5. Verify responses.create called with correct format:
       - text.format.type = "json_schema"
       - text.format.name = schema name
       - text.format.schema = schema definition
       - text.format.strict = True

    Expected Results:
    1. JSON schema correctly formatted for OpenAI
    2. Format includes type, name, schema, and strict flag
    3. Response completes successfully
    4. Schema structure preserved in API call
    """
    # Create mock message
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = '{"name": "John Doe"}'

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_456"
    mock_response.output_text = '{"name": "John Doe"}'
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        json_schema = {
            "name": "user_info",
            "schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }

        request = LLMRequest(
            messages=[{"role": "user", "content": "Extract user info"}],
            output_json_schema=json_schema,
        )

        response = await client.chat(request)

        # The call must succeed before we can inspect what was sent to the API
        assert response.success is True

        # Retrieve the keyword arguments that were passed to responses.create
        call_kwargs = mock_client_instance.responses.create.call_args.kwargs
        # The "text" parameter is how the OpenAI Responses API receives format instructions
        assert "text" in call_kwargs
        # "json_schema" tells OpenAI to validate and constrain the output to a specific structure
        assert call_kwargs["text"]["format"]["type"] == "json_schema"
        # The name identifies the schema so OpenAI can label the output correctly
        assert call_kwargs["text"]["format"]["name"] == "user_info"
        # strict=True means OpenAI will reject any response that does not match the schema exactly
        assert call_kwargs["text"]["format"]["strict"] is True
        # The schema object itself must be forwarded verbatim — OpenAI uses it to validate output structure
        assert call_kwargs["text"]["format"]["schema"] == json_schema["schema"]


# ============================================================================
# LLM-OAPI-004: Tool Calls Handling
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_calls_handling(mock_openai_settings):
    """LLM-OAPI-004: Tool Calls Handling

    Verify that tool calls are properly extracted from OpenAI response.

    Test Steps:
    1. Create mock function_call item:
       - item.type = "function_call"
       - item.name = "get_weather"
       - item.call_id = "call_123"
       - item.arguments = '{"location": "NYC"}'
    2. Mock OpenAI response with function_call in output
    3. Create LLMRequest with tools parameter
    4. Call client.chat(request)
    5. Verify response.tool_calls contains extracted function call

    Expected Results:
    1. Function call properly extracted
    2. tool_call includes name, call_id, and arguments
    3. Arguments properly parsed from JSON string
    4. Tool call added to message history
    5. Response success = True
    """
    # Create mock function call
    mock_function_call = MagicMock()
    mock_function_call.type = "function_call"
    mock_function_call.name = "get_weather"
    mock_function_call.call_id = "call_123"
    mock_function_call.arguments = '{"location": "NYC"}'

    mock_response = MagicMock()
    mock_response.id = "response_789"
    mock_response.output_text = ""
    mock_response.output = [mock_function_call]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        request = LLMRequest(
            messages=[{"role": "user", "content": "What's the weather in NYC?"}],
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
        )

        response = await client.chat(request)

        # The call must succeed even when the model returns a function call instead of text
        assert response.success is True
        # Exactly one tool call was in the response — the client must not drop or duplicate it
        assert response.tool_calls is not None and len(response.tool_calls) == 1
        # The function name tells the caller which tool to invoke
        assert response.tool_calls[0]["name"] == "get_weather"
        # call_id is OpenAI's own identifier — it must be sent back when returning the tool result
        assert response.tool_calls[0]["call_id"] == "call_123"
        # The arguments arrive as a JSON string from OpenAI and must be parsed into a dict
        assert response.tool_calls[0]["arguments"] == {"location": "NYC"}


# ============================================================================
# LLM-OAPI-005: Previous Response ID Chaining
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_previous_response_id_chaining(mock_openai_settings):
    """LLM-OAPI-005: Previous Response ID Chaining

    Verify that previous_response_id is properly passed for stateful conversations.

    Test Steps:
    1. Create mock OpenAI response
    2. Create LLMRequest with previous_response_id = "prev_123"
    3. Call client.chat(request)
    4. Verify responses.create called with:
       - previous_response_id = "prev_123"
    5. Verify response completes successfully

    Expected Results:
    1. previous_response_id passed to API call
    2. Stateful conversation support enabled
    3. Response returned successfully
    4. Chaining parameter preserved
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "Continuing conversation"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_new"
    mock_response.output_text = "Continuing conversation"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        request = LLMRequest(
            messages=[{"role": "user", "content": "Follow up question"}],
            previous_response_id="prev_123",
        )

        response = await client.chat(request)

        # The call must succeed when a previous_response_id is provided
        assert response.success is True

        # Retrieve what was sent to the API so we can inspect the chaining parameter
        call_kwargs = mock_client_instance.responses.create.call_args.kwargs
        # previous_response_id tells OpenAI to continue the conversation from a previous turn
        # without it, the model treats every request as a fresh conversation
        assert call_kwargs["previous_response_id"] == "prev_123"


# ============================================================================
# LLM-OAPI-006: Message History Preservation
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_message_history_preservation(mock_openai_settings):
    """LLM-OAPI-006: Message History Preservation

    Verify that message history is properly maintained in response.

    Test Steps:
    1. Create LLMRequest with multi-turn conversation (3 messages)
    2. Create mock OpenAI response
    3. Call client.chat(request)
    4. Verify response.messages contains:
       - All original messages
       - New assistant message appended
    5. Verify message count = 4 (3 original + 1 new)

    Expected Results:
    1. All original messages preserved
    2. New assistant message added to history
    3. Message order maintained
    4. Total message count correct
    5. Conversation context preserved
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "I'm doing well!"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_history"
    mock_response.output_text = "I'm doing well!"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        request = LLMRequest(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
                {"role": "user", "content": "How are you?"},
            ]
        )

        response = await client.chat(request)

        # The call must succeed when given an existing multi-turn conversation
        assert response.success is True
        # 3 original messages + 1 new assistant reply = 4 total; losing any message breaks context
        assert response.messages is not None
        assert len(response.messages) == 4
        # The first original message must not be lost or moved
        assert response.messages[0]["content"] == "Hello"
        # [-1] would also work here, but [3] makes the 4-message count explicit
        assert response.messages[3]["content"] == "I'm doing well!"


# ============================================================================
# LLM-OAPI-007: Zero Temperature Not Overridden
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_zero_temperature_not_overridden(mock_openai_settings):
    """LLM-OAPI-007: Zero Temperature Not Overridden

    **Zero Temperature Falsy Bug**
    Sends a chat request with temperature=0.0 and verifies the API receives 0.0,
    not the client default (0.7). Basically: "Does the client send zero when you
    ask for zero, or does it silently swap it for the default?"

    Regression note:
        temperature = request.temperature or self.default_temperature
    Python evaluates 0.0 as falsy, so `or` silently substitutes the default (0.7),
    sending a non-deterministic temperature to the API when the caller explicitly
    requested fully deterministic output.

    Test Steps:
    1. Create OpenAIClient with default_temperature = 0.7
    2. Create LLMRequest with temperature = 0.0
    3. Call client.chat(request)
    4. Read the temperature kwarg actually passed to responses.create
    5. Assert it equals 0.0, not 0.7

    Expected Results:
    1. API receives 0.0 — the explicitly requested value
    2. Default temperature 0.7 is not substituted
    3. Falsy zero is not treated as "no preference"
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "response"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_zero_temp"
    mock_response.output_text = "response"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "test"}],
            temperature=0.0,
        )
        await client.chat(request)

        actual = mock_client_instance.responses.create.call_args.kwargs["temperature"]
        # 0.0 is falsy in Python — if `or` is used, the default 0.7 is sent instead
        assert actual == pytest.approx(
            0.0
        ), f"temperature=0.0 → expected 0.0 but API received {actual}"


# ============================================================================
# LLM-OAPI-008: Explicit Temperature Passed Through
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_explicit_temperature_passed_through(mock_openai_settings):
    """LLM-OAPI-008: Explicit Temperature Passed Through

    **Explicit Temperature Forwarding**
    Sends a chat request with temperature=0.5 and verifies the API receives
    exactly 0.5.

    Test Steps:
    1. Create OpenAIClient with default_temperature = 0.7
    2. Create LLMRequest with temperature = 0.5
    3. Call client.chat(request)
    4. Read the temperature kwarg actually passed to responses.create
    5. Assert it equals 0.5

    Expected Results:
    1. API receives 0.5 — the explicitly requested value
    2. Default temperature 0.7 is not substituted
    3. Value is forwarded unchanged
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "response"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_explicit_temp"
    mock_response.output_text = "response"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "test"}],
            temperature=0.5,
        )
        await client.chat(request)

        actual = mock_client_instance.responses.create.call_args.kwargs["temperature"]
        # An explicit value must be forwarded as-is — the client must not alter it
        assert actual == pytest.approx(
            0.5
        ), f"temperature=0.5 → expected 0.5 but API received {actual}"


# ============================================================================
# LLM-OAPI-009: None Temperature Falls Back to Default
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_none_temperature_falls_back_to_default(mock_openai_settings):
    """LLM-OAPI-009: None Temperature Falls Back to Default

    **Default Temperature Fallback**
    Sends a chat request with temperature=None and verifies the API receives
    the client's configured default (0.7). Basically: "When the caller has no
    temperature preference, does the client's default take effect?"

    Test Steps:
    1. Create OpenAIClient with default_temperature = 0.7
    2. Create LLMRequest with temperature = None
    3. Call client.chat(request)
    4. Read the temperature kwarg actually passed to responses.create
    5. Assert it equals 0.7

    Expected Results:
    1. API receives 0.7 — the client's configured default
    2. None is correctly interpreted as "no preference"
    3. Default is applied exactly once
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "response"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_default_temp"
    mock_response.output_text = "response"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "test"}],
            temperature=None,
        )
        await client.chat(request)

        actual = mock_client_instance.responses.create.call_args.kwargs["temperature"]
        # None means "no preference" — the client's default_temperature must be used
        assert actual == pytest.approx(
            0.7
        ), f"temperature=None → expected 0.7 but API received {actual}"


# ============================================================================
# LLM-OAPI-ERR-001: Malformed JSON in Function Arguments
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_malformed_json_in_function_arguments(mock_openai_settings):
    """LLM-OAPI-ERR-001: Malformed JSON in Function Arguments

    Verify that malformed JSON in function call arguments is handled gracefully.

    Test Steps:
    1. Create mock function_call with invalid JSON in arguments
    2. Call client.chat(request)
    3. Expect json.JSONDecodeError or graceful error handling

    Expected Results:
    1. Error is caught and logged
    2. Exception raised or error response returned
    3. No system crash
    4. Clear error message about JSON parsing
    """
    mock_function_call = MagicMock()
    mock_function_call.type = "function_call"
    mock_function_call.name = "get_weather"
    mock_function_call.call_id = "call_invalid"
    mock_function_call.arguments = "{invalid json"  # Malformed JSON

    mock_response = MagicMock()
    mock_response.id = "response_error"
    mock_response.output_text = ""
    mock_response.output = [mock_function_call]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        request = LLMRequest(
            messages=[{"role": "user", "content": "Test"}],
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
        )

        # Malformed JSON in function arguments → json.loads raises JSONDecodeError,
        # which the client catches and re-raises as Exception("OpenAI chat failed: ...")
        with pytest.raises(Exception, match="OpenAI chat failed"):
            await client.chat(request)


# ============================================================================
# LLM-OAPI-ERR-002: API Network Error Handling
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_api_network_error_handling(mock_openai_settings):
    """LLM-OAPI-ERR-002: API Network Error Handling

    Verify that network errors from OpenAI API are handled properly.

    Test Steps:
    1. Mock AsyncOpenAI to raise ConnectionError
    2. Call client.chat(request)
    3. Verify error is propagated or handled gracefully

    Expected Results:
    1. ConnectionError propagated to caller
    2. Or graceful error response returned
    3. No data corruption
    4. Clear error message
    """
    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(
            side_effect=ConnectionError("Network unreachable")
        )
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        request = LLMRequest(messages=[{"role": "user", "content": "Test"}])

        # OpenAI client wraps ConnectionError in a new Exception("OpenAI chat failed: <original>")
        # match= narrows the broad Exception catch to the specific wrapper message
        with pytest.raises(Exception, match="OpenAI chat failed") as exc_info:
            await client.chat(request)

        # The original error message must survive inside the wrapper so the caller knows what failed
        assert "Network unreachable" in str(exc_info.value)


# ============================================================================
# LLM-OAPI-EDGE-001: Empty Tool Calls List
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_empty_tool_calls_list(mock_openai_settings):
    """LLM-OAPI-EDGE-001: Empty Tool Calls List

    Verify handling of response with empty tool_calls list vs None.

    Test Steps:
    1. Create mock response with empty output list
    2. Call client.chat(request)
    3. Verify response.tool_calls is empty list or None

    Expected Results:
    1. No errors from empty output
    2. tool_calls handled as empty list
    3. Response still successful
    4. No IndexError or AttributeError
    """
    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_text = MagicMock()
    mock_text.type = "output_text"
    mock_text.text = "No tools needed"
    mock_message.content = [mock_text]

    mock_response = MagicMock()
    mock_response.id = "response_empty"
    mock_response.output_text = "No tools needed"
    mock_response.output = [mock_message]  # No function_call items

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()

        request = LLMRequest(
            messages=[{"role": "user", "content": "Just chat"}],
            tools=[{"type": "function", "function": {"name": "get_weather"}}],
        )

        response = await client.chat(request)

        # The call must succeed even when the model chose not to use any tools
        assert response.success is True
        # No tool calls were in the response — the client must not fabricate any
        assert (response.tool_calls is None) or (len(response.tool_calls) == 0)
        # The text reply must still be extracted normally even when there are no tool calls
        assert response.content == "No tools needed"


# ============================================================================
# LLM-OAPI-EDGE-002: OpenAIClient.chat() handles tool_calls with unexpected type
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_calls_unexpected_type(mock_openai_settings):
    """LLM-OAPI-EDGE-002: Tool Calls With Unexpected Output Type

    Verify that OpenAIClient.chat() handles response.output as a non-list type without crashing.

    Test Steps:
    1. Mock OpenAI response so output is a dict instead of a list.
    2. Call OpenAIClient.chat() with a valid request.

    Expected Results:
    1. The client does not crash.
    2. response.tool_calls is an empty list or None, handled gracefully.
    """
    mock_function_call = {"type": "function_call", "name": "bad_type"}
    mock_response = MagicMock()
    mock_response.id = "response_unexpected_type"
    mock_response.output_text = ""
    mock_response.output = mock_function_call  # Not a list

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(messages=[{"role": "user", "content": "Hi"}])
        response = await client.chat(request)
        assert isinstance(response.tool_calls, list) or response.tool_calls is None


# ============================================================================
# LLM-OAPI-EDGE-003: OpenAIClient.chat() handles tool_call missing required fields
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_call_missing_fields(mock_openai_settings):
    """LLM-OAPI-EDGE-003: Tool Call Missing Required Fields

    Verify that OpenAIClient.chat() handles function_call items missing name or arguments gracefully.

    Test Steps:
    1. Mock a function_call item where arguments is not a valid JSON string (None).
    2. Call OpenAIClient.chat() with a valid request.

    Expected Results:
    1. json.loads raises TypeError on the non-string arguments value.
    2. The client catches the error and re-raises as Exception("OpenAI chat failed: ...").
    3. No unhandled AttributeError or silent data corruption.
    """
    mock_function_call = MagicMock()
    mock_function_call.type = "function_call"
    mock_function_call.call_id = "call_missing_fields"
    mock_function_call.name = "some_tool"
    # Explicitly set arguments to None — json.loads(None) raises TypeError
    mock_function_call.arguments = None

    mock_response = MagicMock()
    mock_response.id = "response_missing_fields"
    mock_response.output_text = ""
    mock_response.output = [mock_function_call]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(messages=[{"role": "user", "content": "Test"}])
        # json.loads(None) raises TypeError — client wraps it as "OpenAI chat failed"
        with pytest.raises(Exception, match="OpenAI chat failed"):
            await client.chat(request)


# ============================================================================
# LLM-OAPI-EDGE-004: OpenAIClient.chat() handles request with messages=None
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_request_messages_none(mock_openai_settings):
    """LLM-OAPI-EDGE-004: Request With Messages Set to None

    Verify that OpenAIClient.chat() handles an LLMRequest where messages=None without crashing.

    Test Steps:
    1. Create an LLMRequest with messages=None.
    2. Mock OpenAI response with a valid message.
    3. Call OpenAIClient.chat().

    Expected Results:
    1. The client does not crash.
    2. The response contains only the assistant reply in response.messages.
    3. response.success is True.
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "reply"
    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]
    mock_response = MagicMock()
    mock_response.id = "response_none"
    mock_response.output_text = "reply"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(messages=None)
        response = await client.chat(request)
        assert response.success is True
        assert response.messages is not None
        assert len(response.messages) == 1


# ============================================================================
# LLM-OAPI-EDGE-005: OpenAIClient.chat() handles message.content as unexpected type
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_unexpected_content_type(mock_openai_settings):
    """LLM-OAPI-EDGE-005: Message Content With Unexpected Type

    Verify that OpenAIClient.chat() handles message.content as a non-standard type gracefully.

    The SDK normally returns content items as objects with a .type attribute:
        sdk_content.type         → "output_text"  ✅

    Plain dicts are NOT SDK objects — they use keys, not attributes:
        dict_content["type"]     → "output_text"  ✅
        dict_content.type        → AttributeError ❌  ← this is the bug

    With the fix, both are handled:
        content_type = content.get("type") if isinstance(content, dict) else content.type
        → "output_text"  ✅  no crash, correct value

    Test Steps:
    1. Mock OpenAI response so message.content is a list containing a plain dict
       instead of SDK output_text objects.
    2. Call OpenAIClient.chat() with a valid request.

    Expected Results:
    1. The client does not crash with AttributeError.
    2. response.content is a string (possibly empty if no output_text items found).
    """
    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [{"unexpected": "dict"}]  # Not a string

    mock_response = MagicMock()
    mock_response.id = "response_unexpected_content"
    mock_response.output_text = ""
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        dict_content = {"unexpected": "dict"}

        print("\n")
        print("=" * 65)
        print("  LLM-OAPI-EDGE-005: Does chat() crash on dict content items?")
        print("=" * 65)
        print()
        print("  STEP 1 — What the SDK normally returns (SDK object):")
        print("           sdk_content.type        → 'output_text'  ✅")
        print("           sdk_content.text        → 'Hello world'  ✅")
        print()
        print("  STEP 2 — Our dict does NOT have a .type attribute:")
        print(f"           dict_content            = {dict_content}")
        print(
            f"           dict_content['unexpected'] → '{dict_content['unexpected']}'  ✅  (key access works)"
        )
        print("           dict_content.type       → AttributeError ❌  (no such attribute)")
        print()
        print("  STEP 3 — This is what gets passed to the client:")
        print(f"           mock_message.content    = {mock_message.content}")
        print("           Item [0] is a plain dict — the code tries content.type on it")
        print()
        print("  STEP 4 — Calling client.chat(request)...")

        response = await client.chat(request)

        print()
        print(f"  STEP 5 — response.content = {repr(response.content)}")
        print(f"           type: {type(response.content).__name__}")
        print()
        if isinstance(response.content, str):
            print("  ✅ PASS — No crash. response.content is a string.")
            print("           The isinstance guard handled the dict safely.")
        else:
            print("  ❌ BUG  — response.content is not a string.")
            print("           The dict content was not handled gracefully.")
        print("=" * 65)

        assert isinstance(response.content, str)


# ============================================================================
# LLM-OAPI-EDGE-006: OpenAIClient.chat() does not retry on unexpected exceptions
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_unexpected_exception_not_retried(mock_openai_settings):
    """LLM-OAPI-EDGE-006: Unexpected Exception Not Retried

    Verify that OpenAIClient.chat() does not retry when an unexpected RuntimeError occurs.

    Test Steps:
    1. Mock AsyncOpenAI client to raise a RuntimeError on every call to responses.create.
    2. Call OpenAIClient.chat() with a valid request.

    Expected Results:
    1. Exception is propagated to the caller.
    2. responses.create is called exactly once — no retry loop executed.
    """
    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(
            side_effect=RuntimeError("Unexpected error")
        )
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        # RuntimeError is caught by the client's broad except and re-raised as
        # Exception("OpenAI chat failed: ...") — so we match the wrapper, not the original type
        with pytest.raises(Exception, match="OpenAI chat failed"):
            await client.chat(request)
        # No retry logic in this client — responses.create must have been called exactly once
        assert mock_client_instance.responses.create.call_count == 1


# ============================================================================
# LLM-OAPI-EDGE-007: Messages List Not Mutated on Chat
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_messages_list_not_mutated(mock_openai_settings):
    """LLM-OAPI-EDGE-007: Messages List Not Mutated on Chat

    Verify that OpenAIClient.chat() does not mutate the caller's original messages list.

    If the client appends the assistant reply directly to request.messages (instead of a copy),
    the caller's list grows with each call — a subtle state-leak bug.

    Test Steps:
    1. Create a messages list with one user message.
    2. Take a snapshot of the list length before calling chat().
    3. Call client.chat(request).
    4. Compare the caller's list length to the snapshot.

    Expected Results:
    1. The original messages list length is unchanged after chat() returns.
    2. No assistant entry is appended to the caller's list.
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "reply"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_mutation_check"
    mock_response.output_text = "reply"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        original_messages = [{"role": "user", "content": "Hello"}]
        request = LLMRequest(messages=original_messages)

        length_before = len(original_messages)
        await client.chat(request)

        # If the client appends to request.messages directly (not a copy), this will fail
        assert (
            len(original_messages) == length_before
        ), f"original messages list was mutated: length went from {length_before} to {len(original_messages)}"


# ============================================================================
# LLM-OAPI-EDGE-008: Response Messages Independent of Request Messages
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_response_messages_independent_of_request(mock_openai_settings):
    """LLM-OAPI-EDGE-008: Response Messages Independent of Request Messages

    Verify that mutating response.messages after chat() does not affect the caller's input list.

    If response.messages is the same object as request.messages, any post-call mutation
    (e.g. appending a tool result) would corrupt the original list.

    Test Steps:
    1. Create a messages list with one user message.
    2. Call client.chat(request).
    3. Append a new entry to response.messages.
    4. Verify the original messages list is unaffected.

    Expected Results:
    1. response.messages is a distinct object from the original list.
    2. Mutating response.messages does not change the caller's original list.
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "reply"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_independence_check"
    mock_response.output_text = "reply"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        original_messages = [{"role": "user", "content": "Hello"}]
        request = LLMRequest(messages=original_messages)
        length_before = len(original_messages)

        llm_response = await client.chat(request)

        # Mutate the returned list to simulate a caller adding a tool result
        assert llm_response.messages is not None
        llm_response.messages.append({"role": "tool", "content": "tool result"})

        # If response.messages is the same object as original_messages, this will fail
        assert (
            len(original_messages) == length_before
        ), "mutating response.messages affected the caller's original list — they share the same object"


# ============================================================================
# LLM-OAPI-EDGE-009: Second Call Does Not Inherit First Call History
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_second_call_does_not_inherit_first_call_history(mock_openai_settings):
    """LLM-OAPI-EDGE-009: Second Call Does Not Inherit First Call History

    Reusing the same LLMRequest across two calls must not leak the assistant
    reply from call 1 into the input of call 2.

    Bug: input_list = request.messages or []  ← alias, not a copy
         input_list.append(assistant_reply)   ← mutates request.messages
    """
    mock_text_content = MagicMock()
    mock_text_content.type = "output_text"
    mock_text_content.text = "reply"

    mock_message = MagicMock()
    mock_message.type = "message"
    mock_message.role = "assistant"
    mock_message.content = [mock_text_content]

    mock_response = MagicMock()
    mock_response.id = "response_second_call"
    mock_response.output_text = "reply"
    mock_response.output = [mock_message]

    with patch("finbot.core.llm.openai_client.AsyncOpenAI") as mock_async_openai:
        mock_client_instance = AsyncMock()
        mock_client_instance.responses.create = AsyncMock(return_value=mock_response)
        mock_async_openai.return_value = mock_client_instance

        client = OpenAIClient()
        request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
        actual_reply = mock_response.output[0]

        print(f"\n  [before call 1]  request.messages = {request.messages}")

        await client.chat(request)

        sent_call1 = mock_client_instance.responses.create.call_args_list[0].kwargs["input"]
        print(f"  [call 1 → API]   sent {len(sent_call1)} message(s): {sent_call1[:1]}")
        print(
            f"  [call 1 ← API]   role={actual_reply.role}  content='{actual_reply.content[0].text}'"
        )
        print(f"  [after call 1]   request.messages mutated → {request.messages}")

        await client.chat(request)

        sent_call2 = mock_client_instance.responses.create.call_args_list[1].kwargs["input"]
        print(f"  [call 2 → API]   sent {len(sent_call2)} message(s) — expected 1")
        for i, msg in enumerate(sent_call2):
            tag = "(original)" if i == 0 else "(injected by call 1)"
            print(f"                   [{i}] {msg} {tag}")

        assert len(sent_call2) == 1, (
            f"Bug: call 2 received {len(sent_call2)} messages — "
            "assistant reply from call 1 leaked into call 2 via list mutation."
        )


# ============================================================================
# LLM-OAPI-GSI-001: Google Sheets Integration Verification
# ============================================================================
@pytest.mark.unit
def test_google_sheets_integration_verification():
    """LLM-OAPI-GSI-001: Google Sheets Integration Verification

    Verify that OpenAI client test results are properly recorded in Google Sheets.

    Test Steps:
    1. Load environment variables for Google Sheets credentials
    2. Check if GOOGLE_SHEETS_ID and credentials file exist
    3. Connect to Google Sheets using service account credentials
    4. Open the Summary worksheet
    5. Verify the worksheet contains test run data
    6. Verify headers include: timestamp, total_tests, passed, failed
    7. Check LLM Integration Testing worksheet exists
    8. Verify automation_status column exists in the worksheet

    Expected Results:
    1. Google Sheets connection successful
    2. Summary sheet contains recent test run data with proper headers
    3. Test counts are tracked in the summary
    4. LLM Integration Testing worksheet exists
    5. Worksheet has automation_status column for tracking test automation
    6. Integration allows CI/CD pipeline to record test results
    """

    sheet_id = os.getenv("GOOGLE_SHEETS_ID")
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "google-credentials.json")

    if not sheet_id or not os.path.exists(creds_file):
        pytest.skip("Google Sheets credentials not configured")

    try:
        # Connect to Google Sheets
        creds = Credentials.from_service_account_file(
            creds_file, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id)

        # Check Summary sheet exists
        summary_sheet = sheet.worksheet("Summary")
        summary_data = summary_sheet.get_all_values()

        # The pytest_google_sheets.py plugin writes test results here after every run.
        # Row 0 is the header row, so we need at least 2 rows to confirm data was actually written.
        assert len(summary_data) > 1, "Summary sheet should have data"

        # summary_data[0] is the first row — the column headers the plugin creates
        headers = summary_data[0]
        # These four columns are the core metrics the plugin must write after each test run
        assert "timestamp" in headers
        assert "total_tests" in headers
        assert "passed" in headers
        assert "failed" in headers

        # Check LLM Integration Testing worksheet (optional - may not exist yet)
        try:
            llm_sheet = sheet.worksheet("LLM Integration Testing")
            llm_data = llm_sheet.get_all_values()

            if llm_data:
                # The automation_status column tracks which test cases are covered by automated tests
                headers = llm_data[0]
                has_automation_status = any("automation" in h.lower() for h in headers)
                assert has_automation_status, "Should have automation_status column"
        except gspread.exceptions.WorksheetNotFound:
            # Worksheet doesn't exist yet - skip this check
            pass

    except Exception as e:
        pytest.fail(f"Google Sheets verification failed: {e}")
