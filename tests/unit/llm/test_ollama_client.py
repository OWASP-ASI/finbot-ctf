# ==============================================================================
# Ollama Client Test Suite
# ==============================================================================
# User Story: As a developer, I want OllamaClient to reliably communicate with
#             a local Ollama server so that the platform can run AI inference
#             offline without depending on cloud providers.
#
# Acceptance Criteria:
#   1. Loads configuration from settings at instantiation
#   2. Sends correctly formatted chat requests and parses responses
#   3. Extracts tool calls from model output
#   4. Retries on transient network errors, fails fast on logic errors
#   5. Does not mutate the caller's LLMRequest or message list
#   6. Handles malformed API responses without crashing
#
# Test Categories:
#   LLM-CONF-001: Default Configuration Loading
#   LLM-CHAT-001: Successful Chat Completion
#   LLM-CHAT-002: Message History Preservation
#   LLM-CHAT-003: Custom Model and Temperature Override
#   LLM-CHAT-004: Zero Temperature Override Prevention
#   LLM-TOOL-001: Tool Calls Extraction
#   LLM-TOOL-002: Multiple Tool Calls
#   LLM-TOOL-003: Tool Calls In History Are JSON-Serializable
#   LLM-TOOL-004: Tool Calls In History Have Expected Dict Structure
#   LLM-ERR-001: Retry on Timeout Error
#   LLM-ERR-002: Retry Exhaustion
#   LLM-ERR-003: Connection Error Retry
#   LLM-ERR-004: Non-Retryable Error Immediate Failure
#   LLM-JSON-001: JSON Schema Output Formatting
#   LLM-META-001: Response Metadata Extraction
#   LLM-META-002: Missing Metadata Graceful Handling
#   LLM-OLLA-EDGE-001: Empty Message Content Handling
#   LLM-OLLA-EDGE-002: Tool Calls With Message Content
#   LLM-OLLA-EDGE-003: Chat Does Not Mutate Original Messages List
#   LLM-OLLA-EDGE-004: Second Call Does Not Inherit First Call History
#   LLM-OLLA-EDGE-005: response.messages Is None (bug documentation)
#   LLM-OLLA-EDGE-006: Tool Calls With Unexpected Type
#   LLM-OLLA-EDGE-007: Tool Call Missing Required Fields
#   LLM-OLLA-EDGE-008: Request With Messages Set to None
#   LLM-OLLA-EDGE-009: Message Content With Unexpected Type
#   LLM-OLLA-EDGE-010: Unexpected Exception Not Retried
#   LLM-OLLA-GSI-001: Google Sheets Integration Verification
# ==============================================================================

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---- mock ollama  ----
mock_ollama = MagicMock()
mock_ollama.AsyncClient = MagicMock()
sys.modules["ollama"] = mock_ollama
# --------------------------------------------------------------

from finbot.core.llm.ollama_client import OllamaClient
from finbot.core.data.models import LLMRequest

import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import gspread

load_dotenv()


@pytest.fixture(autouse=True)
def _disable_ollama_auto_pull_for_unit_tests(monkeypatch):
    monkeypatch.setattr("finbot.core.llm.ollama_client.settings.LLM_PROVIDER", "openai")


def test_normalizes_openai_style_tool_definitions_for_ollama():
    tools = [
        {
            "type": "function",
            "name": "get_vendor_details",
            "strict": True,
            "description": "Get vendor details",
            "parameters": {
                "type": "object",
                "properties": {"vendor_id": {"type": "integer"}},
                "required": ["vendor_id"],
                "additionalProperties": False,
            },
        }
    ]

    normalized = OllamaClient._normalize_tools(tools)

    assert normalized == [
        {
            "type": "function",
            "function": {
                "name": "get_vendor_details",
                "description": "Get vendor details",
                "parameters": tools[0]["parameters"],
            },
        }
    ]


def test_normalizes_tool_call_history_for_ollama_followup():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "name": "get_vendor_details",
                    "call_id": "ollama_call_0",
                    "arguments": {"vendor_id": 1},
                }
            ],
        },
        {
            "type": "function_call_output",
            "call_id": "ollama_call_0",
            "output": '{"company_name": "Acme"}',
        },
    ]

    normalized = OllamaClient._normalize_messages(messages)

    assert normalized[0] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "get_vendor_details",
                    "arguments": {"vendor_id": 1},
                }
            }
        ],
    }
    assert normalized[1] == {
        "role": "tool",
        "content": '{"company_name": "Acme"}',
        "tool_name": "get_vendor_details",
    }


@pytest.mark.parametrize(
    ("available_models", "should_pull"),
    [
        ([], True),
        ([MagicMock(model="gemma4:e2b")], False),
    ],
)
@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensures_default_ollama_model_available(available_models, should_pull):
    fake_message = AsyncMock()
    fake_message.content = "reply"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "ollama"
        mock_settings.OLLAMA_MODEL = "gemma4:e2b"
        mock_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
        mock_settings.LLM_DEFAULT_TEMPERATURE = 0.7
        mock_settings.LLM_MAX_TOKENS = 5000
        mock_settings.LLM_TIMEOUT = 60
        mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"

        with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
            instance = mock_client.return_value
            instance.list = AsyncMock(return_value=MagicMock(models=available_models))
            instance.pull = AsyncMock(return_value=MagicMock(status="success"))
            instance.chat = AsyncMock(return_value=fake_response)

            client = OllamaClient()
            await client.chat(LLMRequest(messages=[{"role": "user", "content": "hi"}]))

            instance.list.assert_awaited_once()
            if should_pull:
                instance.pull.assert_awaited_once_with("gemma4:e2b")
            else:
                instance.pull.assert_not_awaited()
            assert instance.chat.await_args.kwargs["model"] == "gemma4:e2b"


# ============================================================================
# LLM-CONF-001: Default Configuration Loading
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_default_configuration_loading():
    """LLM-CONF-001: Default Configuration Loading

    Verify that OllamaClient loads default configuration from settings correctly.

    Test Steps:
    1. Create OllamaClient instance without custom parameters
    2. Verify default_model is loaded from settings.OLLAMA_MODEL when provider is ollama
    3. Verify default_temperature is loaded from settings.LLM_DEFAULT_TEMPERATURE
    4. Verify host is set to OLLAMA_BASE_URL or defaults to "https://localhost:11434"
    5. Verify AsyncClient is initialized with correct host and timeout

    Expected Results:
    1. OllamaClient instance created successfully
    2. default_model matches settings value
    3. default_temperature matches settings value
    4. host matches settings or defaults correctly
    5. AsyncClient configured with proper connection parameters
    """
    with patch("finbot.core.llm.ollama_client.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "ollama"
        mock_settings.OLLAMA_MODEL = "gemma4:e2b"
        mock_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
        mock_settings.LLM_DEFAULT_TEMPERATURE = 0.7
        mock_settings.LLM_TIMEOUT = 60
        mock_settings.OLLAMA_BASE_URL = "https://custom-ollama:11434"

        with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_async_client:
            client = OllamaClient()

            # The client must store the model name from settings — used as default for every request
            assert client.default_model == "gemma4:e2b"
            # Temperature controls response randomness (0=deterministic, 1=creative); must match settings
            assert client.default_temperature == pytest.approx(0.7)
            # The Ollama server URL must be read from OLLAMA_BASE_URL so the client knows where to connect
            assert client.host == "https://custom-ollama:11434"
            # AsyncClient must be constructed with the correct host+timeout — wrong values cause connection failures
            mock_async_client.assert_called_once_with(
                host="https://custom-ollama:11434",
                timeout=60
            )


# ============================================================================
# LLM-CHAT-001: Successful Chat Completion
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_successful_chat_completion():
    """LLM-CHAT-001: Successful Chat Completion

    Verify that basic chat completion works with valid input messages.

    Test Steps:
    1. Create mock response with:
       - message.content = "hello"
       - message.tool_calls = None
    2. Configure AsyncClient mock to return fake_response
    3. Create OllamaClient instance
    4. Create LLMRequest with:
       - messages = [{"role": "user", "content": "hi"}]
    5. Call client.chat(request)
    6. Verify response fields:
       - success = True
       - provider = "ollama"
       - content = "hello"
       - messages length = 2 (user + assistant)

    Expected Results:
    1. Chat request completes successfully
    2. Response contains correct content
    3. Provider set to "ollama"
    4. Message history includes both user and assistant messages
    5. No errors or exceptions raised
    """
    fake_message = AsyncMock()
    fake_message.content = "hello"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message
    fake_response.total_duration = 1000
    fake_response.load_duration = 100
    fake_response.eval_count = 50

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()

        request = LLMRequest(
            messages=[{"role": "user", "content": "hi"}]
        )

        response = await client.chat(request)

        # The call must complete without raising an exception
        assert response.success is True
        assert response.messages is not None
        # The provider field identifies which backend produced this response — used for routing/logging
        assert response.provider == "ollama"
        # The LLM's reply text must be passed through unchanged
        assert response.content == "hello"
        # The returned history must include both the input user message and the new assistant reply
        assert len(response.messages) == 2
        # First message must be the user turn we sent in
        assert response.messages[0]["role"] == "user"
        # Second message must be the assistant's reply appended by the client
        assert response.messages[1]["role"] == "assistant"


# ============================================================================
# LLM-CHAT-002: Message History Preservation
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_message_history_preservation():
    """LLM-CHAT-002: Message History Preservation

    Verify that message history is properly maintained across chat interactions.

    Test Steps:
    1. Create mock response with content = "I'm doing well, thanks!"
    2. Create LLMRequest with multi-turn conversation:
       - Message 1: {"role": "user", "content": "Hello"}
       - Message 2: {"role": "assistant", "content": "Hi there!"}
       - Message 3: {"role": "user", "content": "How are you?"}
    3. Call client.chat(request)
    4. Verify response.messages contains all 4 messages (3 original + 1 new assistant)
    5. Verify order and content of all messages preserved

    Expected Results:
    1. Chat completes successfully
    2. All previous messages preserved in order
    3. New assistant message appended to history
    4. Total message count = 4
    5. Message roles and content match expected values
    """
    fake_message = AsyncMock()
    fake_message.content = "I'm doing well, thanks!"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()

        request = LLMRequest(
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"}
            ]
        )

        response = await client.chat(request)

        # The call must succeed when given an existing multi-turn conversation
        assert response.success is True
        # 3 original messages + 1 new assistant reply = 4 total; losing any message breaks context
        assert response.messages is not None
        assert len(response.messages) == 4
        # Original messages must appear first, in original order
        assert response.messages[0]["content"] == "Hello"
        assert response.messages[1]["content"] == "Hi there!"
        assert response.messages[2]["content"] == "How are you?"
        # The new assistant reply must be appended at the end
        assert response.messages[3]["content"] == "I'm doing well, thanks!"


# ============================================================================
# LLM-CHAT-003: Custom Model and Temperature Override
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_custom_model_temperature_override():
    """LLM-CHAT-003: Custom Model and Temperature Override

    Verify that request-level model and temperature parameters override defaults.

    Test Steps:
    1. Set default configuration:
       - LLM_DEFAULT_MODEL = "llama3.2"
       - LLM_DEFAULT_TEMPERATURE = 0.7
    2. Create LLMRequest with overrides:
       - model = "codellama"
       - temperature = 0.2
    3. Create mock response
    4. Call client.chat(request)
    5. Verify AsyncClient.chat called with:
       - model = "codellama" (not default)
       - options.temperature = 0.2 (not default)

    Expected Results:
    1. Request-level parameters override defaults
    2. AsyncClient.chat receives custom model name
    3. AsyncClient.chat receives custom temperature
    4. Response completes successfully
    5. No errors from parameter override
    """
    fake_message = AsyncMock()
    fake_message.content = "Code generated"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.settings") as mock_settings:
        mock_settings.LLM_DEFAULT_MODEL = "llama3.2"
        mock_settings.LLM_DEFAULT_TEMPERATURE = 0.7
        mock_settings.LLM_TIMEOUT = 60
        mock_settings.LLM_MAX_TOKENS = 4096

        with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
            instance = mock_client.return_value
            instance.chat = AsyncMock(return_value=fake_response)

            client = OllamaClient()

            request = LLMRequest(
                messages=[{"role": "user", "content": "Write a function"}],
                model="codellama",
                temperature=0.2
            )

            response = await client.chat(request)

            assert response.success is True

            # Verify chat was called with custom parameters
            call_args = instance.chat.call_args
            assert call_args.kwargs["model"] == "codellama"
            assert call_args.kwargs["options"]["temperature"] == pytest.approx(0.2)

# ============================================================================
# LLM-CHAT-004: Zero Temperature Override Prevention
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_zero_temperature_not_overridden():
    """LLM-CHAT-004: Zero Temperature Override Prevention

    Verify that temperature=0.0 is passed through to AsyncClient unchanged.

    Regression test for:
        temperature = request.temperature or self.default_temperature
    When request.temperature=0.0, `or` evaluates to the default because 0.0 is falsy.

    Test Steps:
    1. Create OllamaClient with default_temperature = 0.7
    2. Create LLMRequest with temperature = 0.0 (explicit zero)
    3. Call client.chat(request)
    4. Inspect options["temperature"] passed to AsyncClient.chat

    Expected Results:
    1. options["temperature"] == 0.0
    2. Default temperature (0.7) is NOT substituted
    3. Deterministic output behavior honored
    4. No error or warning raised
    """
    fake_message = AsyncMock()
    fake_message.content = "deterministic output"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.settings") as mock_settings:
        mock_settings.LLM_DEFAULT_MODEL = "llama3.2"
        mock_settings.LLM_DEFAULT_TEMPERATURE = 0.7
        mock_settings.LLM_TIMEOUT = 60
        mock_settings.LLM_MAX_TOKENS = 4096

        with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
            instance = mock_client.return_value
            instance.chat = AsyncMock(return_value=fake_response)

            client = OllamaClient()

            request = LLMRequest(
                messages=[{"role": "user", "content": "be deterministic"}],
                temperature=0.0,
            )

            await client.chat(request)

            actual = instance.chat.call_args.kwargs["options"]["temperature"]
            # We use pytest.approx instead of == to safely compare floating-point numbers.
            # The default temperature is 0.7, which is nowhere near 0.0, so the bug is still caught.
            assert actual == pytest.approx(0.0), (
                f"Expected temperature=0.0 but got {actual}. "
                "Bug: `or` treats 0.0 as falsy and substitutes the default."
            )
# ============================================================================
# LLM-TOOL-001: Tool Calls Extraction
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_calls_extraction():
    """LLM-TOOL-001: Tool Calls Extraction

    Verify that tool calls are properly extracted and formatted from LLM response.

    Test Steps:
    1. Create mock tool call:
       - function.name = "get_weather"
       - function.arguments = {"location": "San Francisco"}
    2. Create mock response with message.tool_calls = [mock_tool_call]
    3. Create LLMRequest with tools parameter
    4. Call client.chat(request)
    5. Verify response.tool_calls contains:
       - name = "get_weather"
       - call_id = "ollama_call_0"
       - arguments = {"location": "San Francisco"}

    Expected Results:
    1. Chat completes successfully
    2. Tool call properly extracted from response
    3. Tool call fields correctly formatted
    4. call_id generated with proper format
    5. Arguments preserved as dict
    """
    mock_tool_call = AsyncMock()
    mock_tool_call.function.name = "get_weather"
    mock_tool_call.function.arguments = {"location": "San Francisco"}

    fake_message = AsyncMock()
    fake_message.content = ""
    fake_message.tool_calls = [mock_tool_call]

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()

        request = LLMRequest(
            messages=[{"role": "user", "content": "What's the weather in San Francisco?"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        }
                    }
                }
            }]
        )

        response = await client.chat(request)

        # The call must succeed even when the model decides to call a tool instead of replying with text
        assert response.success is True
        assert response.messages is not None
        # Exactly one tool call was in the response — the client must not drop or duplicate it
        assert len(response.tool_calls or []) == 1
        # If [response.tool_calls]is not `None`, use it; otherwise, use an empty list. This ensures [tool_calls]
        # is always a list, so you can safely use it in the next lines.
        tool_calls = response.tool_calls or []
        # The function name tells the caller which tool to invoke
        assert tool_calls[0]["name"] == "get_weather"
        # The call_id links this tool call to its result when sending the result back to the model
        assert tool_calls[0]["call_id"] == "ollama_call_0"
        # The arguments dict is what the tool function receives — it must be preserved exactly
        assert tool_calls[0]["arguments"] == {"location": "San Francisco"}


# ============================================================================
# LLM-TOOL-002: Multiple Tool Calls
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_multiple_tool_calls():
    """LLM-TOOL-002: Multiple Tool Calls

    Verify that multiple tool calls in a single response are handled correctly.

    Test Steps:
    1. Create two mock tool calls:
       - Tool 1: get_weather(location="NYC")
       - Tool 2: get_weather(location="LA")
    2. Set message.tool_calls = [tool1, tool2]
    3. Call client.chat(request)
    4. Verify response.tool_calls contains 2 items
    5. Verify each tool call has unique call_id:
       - call_id = "ollama_call_0"
       - call_id = "ollama_call_1"
    6. Verify both tool calls preserved correctly

    Expected Results:
    1. Both tool calls extracted successfully
    2. Each tool call has unique sequential call_id
    3. All tool call parameters preserved
    4. Response success = True
    5. Tool calls in same order as response
    """
    mock_tool_call_1 = AsyncMock()
    mock_tool_call_1.function.name = "get_weather"
    mock_tool_call_1.function.arguments = {"location": "NYC"}

    mock_tool_call_2 = AsyncMock()
    mock_tool_call_2.function.name = "get_weather"
    mock_tool_call_2.function.arguments = {"location": "LA"}

    fake_message = AsyncMock()
    fake_message.content = ""
    fake_message.tool_calls = [mock_tool_call_1, mock_tool_call_2]

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()

        request = LLMRequest(
            messages=[{"role": "user", "content": "Compare weather in NYC and LA"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather"
                }
            }]
        )

        response = await client.chat(request)

        # Both tool calls must be extracted — dropping one would silently skip a function call
        assert response.success is True
        assert len(response.tool_calls or []) == 2
        # If [response.tool_calls]is not `None`, use it; otherwise, use an empty list. This ensures [tool_calls]
        # is always a list, so you can safely use it in the next lines.
        tool_calls = response.tool_calls or []
        # Each tool call gets a unique sequential ID so results can be matched back to their call
        assert tool_calls[0]["call_id"] == "ollama_call_0"
        # Arguments for the first tool call must not be mixed up with the second
        assert tool_calls[0]["arguments"] == {"location": "NYC"}
        assert tool_calls[1]["call_id"] == "ollama_call_1"
        assert tool_calls[1]["arguments"] == {"location": "LA"}

# ============================================================================
# LLM-TOOL-003: Tool Calls In History Are JSON-Serializable
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_calls_in_history_are_json_serializable():
    """LLM-TOOL-003: Tool Calls In History Are JSON-Serializable

    Verify that tool_calls stored in the assistant history entry are plain
    JSON-serializable dicts, not raw Ollama SDK objects.

    Regression test for:
        history_entry["tool_calls"] = message.tool_calls
    message.tool_calls contains raw SDK objects. Passing this history back
    to AsyncClient.chat() on a follow-up call will fail serialization.

    Test Steps:
    1. Create mock tool call with function name and arguments
    2. Set message.tool_calls = [mock_tool_call]
    3. Call client.chat(request)
    4. Inspect response.messages[-1]["tool_calls"]
    5. Attempt json.dumps() on the stored tool_calls

    Expected Results:
    1. response.messages[-1] contains "tool_calls" key
    2. json.dumps(tool_calls) succeeds without TypeError
    3. Tool calls are plain dicts, not SDK objects
    4. Follow-up calls reusing message history will not fail
    """
    import json as _json

    mock_tool_call = AsyncMock()
    mock_tool_call.function.name = "get_balance"
    mock_tool_call.function.arguments = {"account_id": "123"}

    fake_message = AsyncMock()
    fake_message.content = ""
    fake_message.tool_calls = [mock_tool_call]

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "What's my balance?"}],
            tools=[{"type": "function", "function": {"name": "get_balance"}}],
        )

        response = await client.chat(request)

        # Check that messages is not None before indexing into it — otherwise the next line would crash
        if response.messages is not None:
            assistant_message = response.messages[-1]
            # The history entry must record which tools were called so a follow-up prompt can reference them
            assert "tool_calls" in assistant_message
        else:
            pytest.fail("response.messages is None, cannot access assistant_message")

        # json.dumps() simulates what happens when this history is sent back to the API on the next turn.
        # If the client stored raw SDK objects instead of plain dicts, this raises a TypeError.
        try:
            _json.dumps(assistant_message["tool_calls"])
        except TypeError as exc:
            pytest.fail(
                f"Bug: tool_calls in history are not JSON-serializable: {exc}. "
                "Raw SDK objects were stored instead of plain dicts."
            )


# ============================================================================
# LLM-TOOL-004: Tool Calls In History Have Expected Dict Structure
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_calls_in_history_have_expected_dict_structure():
    """LLM-TOOL-004: Tool Calls In History Have Expected Dict Structure

    Verify that each tool_call entry in message history is a plain dict
    with keys: name, call_id, arguments — matching response.tool_calls format.

    Test Steps:
    1. Create mock tool call
    2. Call client.chat(request)
    3. Inspect response.messages[-1]["tool_calls"][0]
    4. Verify it is a dict with the expected keys

    Expected Results:
    1. tool_call entry is type dict (not AsyncMock or SDK object)
    2. Has key "name"
    3. Has key "call_id"
    4. Has key "arguments"
    """
    mock_tool_call = AsyncMock()
    mock_tool_call.function.name = "get_balance"
    mock_tool_call.function.arguments = {"account_id": "123"}

    fake_message = AsyncMock()
    fake_message.content = ""
    fake_message.tool_calls = [mock_tool_call]

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "check balance"}],
            tools=[{"type": "function", "function": {"name": "get_balance"}}],
        )

        response = await client.chat(request)

        # Check that messages is not None before indexing into it — otherwise the next line would crash
        assert response.messages is not None
        assistant_message = response.messages[-1]
        tool_calls_in_history = assistant_message.get("tool_calls", [])

        # Exactly one tool call was made, so the history must record exactly one
        assert len(tool_calls_in_history) == 1
        tc = tool_calls_in_history[0]
        # Must be a plain dict — raw SDK objects cannot be sent back to the API on the next turn
        assert isinstance(tc, dict), (
            f"Bug: tool_call in history is {type(tc).__name__}, expected dict."
        )
        # "name" tells the caller which function was invoked
        assert "name" in tc
        # "call_id" links this call to its result when the result is sent back to the model
        assert "call_id" in tc
        # "arguments" holds the parameters that were passed to the function
        assert "arguments" in tc
        
# ============================================================================
# LLM-ERR-001: Retry on Timeout Error
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_on_timeout_error():
    """LLM-ERR-001: Retry on Timeout Error

    Verify that transient TimeoutError triggers retry logic and eventually succeeds.

    Test Steps:
    1. Configure AsyncClient.chat to:
       - First call: raise TimeoutError("Connection timeout")
       - Second call: return successful response
    2. Create LLMRequest with basic message
    3. Call client.chat(request)
    4. Verify retry mechanism activated
    5. Verify final response is successful
    6. Verify AsyncClient.chat called exactly 2 times

    Expected Results:
    1. First attempt fails with TimeoutError
    2. Retry mechanism triggers automatically
    3. Second attempt succeeds
    4. Final response.content = "ok"
    5. Total attempts = 2
    6. No exception raised to caller
    """
    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value

        successful_message = AsyncMock()
        successful_message.content = "ok"
        successful_message.tool_calls = None

        successful_response = AsyncMock()
        successful_response.message = successful_message

        instance.chat = AsyncMock(
            side_effect=[
                TimeoutError("Connection timeout"),
                successful_response,
            ]
        )

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

        response = await client.chat(request)

        # Despite the first attempt failing, the retry should have recovered
        assert response.success is True
        # The retry must have returned the successful response, not the error
        assert response.content == "ok"
        # First attempt failed + one retry = 2 total calls to AsyncClient.chat
        assert instance.chat.call_count == 2


# ============================================================================
# LLM-ERR-002: Retry Exhaustion
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_exhaustion():
    """LLM-ERR-002: Retry Exhaustion

    Verify that retries are exhausted after max_retries attempts and error is raised.

    Test Steps:
    1. Configure AsyncClient.chat to always raise TimeoutError
    2. Create LLMRequest with basic message
    3. Attempt client.chat(request)
    4. Expect TimeoutError to be raised
    5. Verify retry mechanism attempted max_retries times
    6. Verify total attempts = max_retries + 1 (initial + retries)

    Expected Results:
    1. Initial attempt fails
    2. Retry mechanism attempts 3 retries (default max_retries=3)
    3. All retry attempts fail
    4. TimeoutError propagated to caller
    5. Total attempts = 4 (1 initial + 3 retries)
    6. No infinite retry loop
    """
    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(side_effect=TimeoutError("Persistent timeout"))

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

        with pytest.raises(TimeoutError):
            await client.chat(request)

        # default max_retries=3 → total attempts = 4
        assert instance.chat.call_count == 4


# ============================================================================
# LLM-ERR-003: Connection Error Retry
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_connection_error_retry():
    """LLM-ERR-003: Connection Error Retry

    Verify that ConnectionError is treated as retryable and triggers retry logic.

    Test Steps:
    1. Configure AsyncClient.chat to:
       - First call: raise ConnectionError("Network unreachable")
       - Second call: return successful response
    2. Create LLMRequest with basic message
    3. Call client.chat(request)
    4. Verify retry triggered on ConnectionError
    5. Verify successful response after retry

    Expected Results:
    1. ConnectionError identified as retryable
    2. Retry mechanism activates
    3. Second attempt succeeds
    4. Response returned successfully
    5. Total attempts = 2
    """
    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value

        successful_message = AsyncMock()
        successful_message.content = "recovered"
        successful_message.tool_calls = None

        successful_response = AsyncMock()
        successful_response.message = successful_message

        instance.chat = AsyncMock(
            side_effect=[
                ConnectionError("Network unreachable"),
                successful_response,
            ]
        )

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        response = await client.chat(request)

        # ConnectionError must be treated the same as TimeoutError — both are transient network issues
        assert response.success is True
        # The retry must return the successful response content
        assert response.content == "recovered"
        # First attempt failed + one retry = 2 total calls
        assert instance.chat.call_count == 2


# ============================================================================
# LLM-ERR-004: Non-Retryable Error Immediate Failure
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_non_retryable_error_immediate_failure():
    """LLM-ERR-004: Non-Retryable Error Immediate Failure

    Verify that non-retryable errors fail immediately without retry attempts.

    Test Steps:
    1. Configure AsyncClient.chat to raise ValueError("Invalid request")
    2. Create LLMRequest with basic message
    3. Attempt client.chat(request)
    4. Expect ValueError raised immediately
    5. Verify AsyncClient.chat called only once (no retries)

    Expected Results:
    1. ValueError identified as non-retryable
    2. No retry attempts made
    3. Error propagated immediately
    4. Total attempts = 1
    5. Fast failure for permanent errors
    """
    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(side_effect=ValueError("Invalid model"))

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with pytest.raises(ValueError):
            await client.chat(request)

        # A ValueError means the request itself is wrong — retrying won't help, so there must be no retries
        assert instance.chat.call_count == 1


# ============================================================================
# LLM-JSON-001: JSON Schema Output Formatting
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_json_schema_output_formatting():
    """LLM-JSON-001: JSON Schema Output Formatting

    Verify that output_json_schema is properly passed to AsyncClient.

    Test Steps:
    1. Define JSON schema:
       - name = "user_info"
       - schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    2. Create LLMRequest with output_json_schema
    3. Create mock response
    4. Call client.chat(request)
    5. Verify AsyncClient.chat called with:
       - format = schema definition

    Expected Results:
    1. output_json_schema extracted from request
    2. format parameter passed to AsyncClient.chat
    3. Schema structure preserved
    4. Response completes successfully
    5. JSON formatting enforced
    """
    fake_message = AsyncMock()
    fake_message.content = '{"name": "John Doe"}'
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()

        json_schema = {
            "name": "user_info",
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"}
                },
                "required": ["name"]
            }
        }

        request = LLMRequest(
            messages=[{"role": "user", "content": "Extract user info"}],
            output_json_schema=json_schema
        )

        response = await client.chat(request)

        assert response.success is True

        # Verify format parameter was set
        call_args = instance.chat.call_args
        assert "format" in call_args.kwargs
        assert call_args.kwargs["format"] == json_schema["schema"]


# ============================================================================
# LLM-META-001: Response Metadata Extraction
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_response_metadata_extraction():
    """LLM-META-001: Response Metadata Extraction

    Verify that response metadata (durations, token counts) is properly extracted.

    Test Steps:
    1. Create mock response with attributes:
       - total_duration = 5000
       - load_duration = 500
       - eval_count = 100
    2. Call client.chat(request)
    3. Verify response.metadata contains:
       - total_duration = 5000
       - load_duration = 500
       - eval_count = 100

    Expected Results:
    1. Metadata fields extracted from response
    2. All duration values preserved
    3. Token count (eval_count) captured
    4. Metadata accessible in response object
    5. No errors if metadata fields missing
    """
    fake_message = AsyncMock()
    fake_message.content = "response"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message
    fake_response.total_duration = 5000
    fake_response.load_duration = 500
    fake_response.eval_count = 100

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        response = await client.chat(request)

        # The chat call itself must succeed before we can inspect metadata
        assert response.success is True
        assert response.metadata is not None
        # total_duration = how long the full request took (nanoseconds from Ollama)
        assert response.metadata["total_duration"] == 5000
        # load_duration = time spent loading the model into memory
        assert response.metadata["load_duration"] == 500
        # eval_count = number of tokens generated — useful for cost/performance tracking
        assert response.metadata["eval_count"] == 100


# ============================================================================
# LLM-META-002: Missing Metadata Graceful Handling
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_missing_metadata_graceful_handling():
    """LLM-META-002: Missing Metadata Graceful Handling

    Verify that missing metadata attributes don't cause errors.

    Test Steps:
    1. Create mock response WITHOUT metadata attributes:
       - No total_duration
       - No load_duration
       - No eval_count
    2. Call client.chat(request)
    3. Verify response completes successfully
    4. Verify response.metadata contains None values for missing fields

    Expected Results:
    1. No AttributeError raised
    2. Response success = True
    3. Metadata dict created with None values
    4. Graceful degradation when metadata unavailable
    5. Core functionality unaffected
    """
    fake_message = AsyncMock()
    fake_message.content = "response"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message
    # Explicitly remove metadata attributes
    del fake_response.total_duration
    del fake_response.load_duration
    del fake_response.eval_count

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        response = await client.chat(request)

        # The call must not crash just because metadata fields are absent
        assert response.success is True
        assert response.metadata is not None
        # Missing fields must be stored as None rather than raising an AttributeError
        assert response.metadata.get("total_duration") is None
        assert response.metadata.get("load_duration") is None
        assert response.metadata.get("eval_count") is None

# ============================================================================
# LLM-OLLA-EDGE-001: Empty Message Content Handling
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_empty_message_content_handling():
    """LLM-OLLA-EDGE-001: Empty Message Content Handling

    Verify that responses with empty content are handled correctly.

    Test Steps:
    1. Create mock response with:
       - message.content = None
       - message.tool_calls = None
    2. Call client.chat(request)
    3. Verify response.content = "" (empty string, not None)
    4. Verify response.success = True
    5. Verify message history updated with empty content

    Expected Results:
    1. None content converted to empty string
    2. No errors from empty content
    3. Response marked as successful
    4. Message history remains valid
    5. Graceful handling of edge case
    """
    fake_message = AsyncMock()
    fake_message.content = None
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        response = await client.chat(request)

        # A None reply from the model must not crash the client
        assert response.success is True
        # None content must be normalized to an empty string, not left as None
        assert response.content == ""
        # The message history must still be updated even when content is empty
        assert response.messages is not None
        assert len(response.messages) == 2


# ============================================================================
# LLM-OLLA-EDGE-002: Tool Calls With Message Content
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_calls_with_message_content():
    """LLM-OLLA-EDGE-002: Tool Calls With Message Content

    Verify that responses containing both tool calls and message content work correctly.

    Test Steps:
    1. Create mock tool call for get_weather
    2. Create mock response with:
       - message.content = "Let me check the weather for you."
       - message.tool_calls = [weather_tool_call]
    3. Call client.chat(request)
    4. Verify response contains both:
       - content = "Let me check the weather for you."
       - tool_calls with weather function
    5. Verify message history includes tool_calls

    Expected Results:
    1. Both content and tool calls extracted
    2. Message history entry includes tool_calls field
    3. Response.content preserved
    4. Response.tool_calls properly formatted
    5. Both pieces of information available to caller
    """
    mock_tool_call = AsyncMock()
    mock_tool_call.function.name = "get_weather"
    mock_tool_call.function.arguments = {"location": "Boston"}

    fake_message = AsyncMock()
    fake_message.content = "Let me check the weather for you."
    fake_message.tool_calls = [mock_tool_call]

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "What's the weather in Boston?"}],
            tools=[{"type": "function", "function": {"name": "get_weather"}}]
        )

        response = await client.chat(request)

        # The call must succeed when the response contains both text and a tool call at the same time
        assert response.success is True
        # The text content must be preserved — it tells the user what the model is doing
        assert response.content == "Let me check the weather for you."
        # The tool call must also be extracted — one must not be dropped in favor of the other
        # If [response.tool_calls]is not `None`, use it; otherwise, use an empty list. This ensures [tool_calls]
        # is always a list, so you can safely use it in the next lines.
        tool_calls = response.tool_calls or []
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "get_weather"
        
        # [-1] means "the last message in the list" — after chat(), that is always the assistant reply just added
        # The history entry must record the tool call so the model can receive the tool result on the next turn
        assert response.messages is not None
        assistant_message = response.messages[-1]
        assert "tool_calls" in assistant_message

# ============================================================================
# LLM-OLLA-EDGE-003: Chat Does Not Mutate Original Messages List
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_chat_does_not_mutate_original_messages_list():
    """LLM-OLLA-EDGE-003: Chat Does Not Mutate Original Messages List

    Verify that chat() does not modify request.messages or the list the
    caller originally passed in.

    Regression test for:
        messages = request.messages or []   # reference, not copy
        messages.append(history_entry)      # mutates original list

    Test Steps:
    1. Create LLMRequest with messages=[{"role": "user", "content": "hello"}]
    2. Store reference to original list
    3. Call client.chat(request)
    4. Verify original list is unchanged (length still 1)
    5. Verify request.messages is unchanged

    Expected Results:
    1. len(original_messages) == 1 after chat()
    2. len(request.messages) == 1 after chat()
    3. No assistant reply appended to caller's list
    """
    fake_message = AsyncMock()
    fake_message.content = "reply"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()

        original_messages = [{"role": "user", "content": "hello"}]
        request = LLMRequest(messages=original_messages)

        print("\n")
        print("=" * 65)
        print("  LLM-OLLA-EDGE-003: Does chat() mutate request.messages?")
        print("=" * 65)
        print()
        print("  👤 User creates a request with 1 message: 'hello'")
        print(f"     request.messages = {list(request.messages or [])}")
        print(f"     Count: {len(request.messages or [])} message(s)")
        print()
        print("  📡 Calling client.chat(request)...")

        await client.chat(request)

        print()
        print("  🤖 Ollama replied: 'reply'")
        print()
        print("  👤 User checks their original request object...")
        print(f"     request.messages = {list(request.messages or [])}")
        print(f"     Count: {len(request.messages or [])} message(s)")
        print()
        if request.messages is not None and len(request.messages) == 1:
            print("  ✅ PASS — request.messages still has 1 message. Not touched.")
        else:
            print("  ❌ BUG  — request.messages now has 2 messages!")
            print("           The assistant reply snuck in. The user never asked for this.")
            print("           chat() is secretly modifying the input it was given.")
        print("=" * 65)

        assert len(original_messages) == 1, (
            f"Bug: original_messages was mutated — now has {len(original_messages)} items. "
            "chat() must copy the list, not hold a reference."
        )
        assert request.messages is not None
        assert len(request.messages) == 1, (
            f"Bug: request.messages was mutated — now has {len(request.messages)} items."
        )


# ============================================================================
# LLM-OLLA-EDGE-004: Second Call Does Not Inherit First Call History
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_second_call_does_not_inherit_first_call_history():
    """LLM-OLLA-EDGE-004: Second Call Does Not Inherit First Call History

    Verify that reusing the same LLMRequest object across two chat() calls
    does not leak the assistant reply from call 1 into the input of call 2.

    Test Steps:
    1. Create LLMRequest with 1 user message
    2. Call client.chat(request) — first call
    3. Call client.chat(request) — second call with same request object
    4. Inspect messages argument of the second AsyncClient.chat call
    5. Verify it contains only 1 message (not 2 or 3)

    Expected Results:
    1. Second call's messages input has exactly 1 item
    2. Assistant reply from call 1 is NOT present in call 2's input
    3. Conversation context is not corrupted across calls
    """
    fake_message = AsyncMock()
    fake_message.content = "reply"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "hello"}])

        print("\n")
        print("=" * 65)
        print("  LLM-OLLA-EDGE-004: Does call 2 inherit history from call 1?")
        print("=" * 65)
        print()
        print("  STEP 1 — User creates a request with 1 message")
        print(f"           request.messages = {list(request.messages or [])}")
        print(f"           Count: {len(request.messages or [])} message(s)")
        print()
        print("  STEP 2 — First call: client.chat(request)")
        print("           Inside chat(), the code does:")
        print("             messages = request.messages or []  ← grabs a reference (or copy)")
        print("             ... sends messages to Ollama ...")
        print("             messages.append(assistant_reply)   ← appends to that list")

        await client.chat(request)

        first_call_messages = instance.chat.call_args_list[0].kwargs["messages"]
        print()
        print(f"           Ollama was sent:   {first_call_messages}  ({len(first_call_messages)} msg)")
        print("           Ollama replied:    'reply'")
        print()
        print("  STEP 3 — Inspect request.messages after call 1")
        print(f"           request.messages = {list(request.messages or [])}")
        print(f"           Count: {len(request.messages or [])} message(s)")
        if len(request.messages or []) == 1:
            print("           ✅ Still 1 — the list was copied, not referenced")
        else:
            print("           ⚠️  Now 2 — the assistant reply was appended into request.messages")
            print("           The request object the user holds has been silently changed.")
        print()
        print("  STEP 4 — Second call: client.chat(request)  ← same object reused")
        print("           Inside chat(), the code does:")
        print("             messages = request.messages or []  ← what does it grab now?")
        print(f"           request.messages currently = {list(request.messages or [])}")
        print("             ... sends messages to Ollama ...")

        await client.chat(request)

        second_call_messages = instance.chat.call_args_list[1].kwargs["messages"]
        print()
        print(f"           Ollama was sent:   {second_call_messages}  ({len(second_call_messages)} msg)")
        print()
        print("  STEP 5 — Was call 2 clean?")
        print(f"           Expected: 1 message  |  Actual: {len(second_call_messages)} message(s)")
        if len(second_call_messages) == 1:
            print("           ✅ PASS — Call 2 sent only the original message. Clean slate.")
        else:
            print("           ❌ BUG  — Call 2 carried over the assistant reply from call 1.")
            print("                     The list was never copied — it was mutated in place.")
        print()
        print(f"  FINAL state of request.messages: {list(request.messages or [])}  ({len(request.messages or [])} msg)")
        print("=" * 65)

        assert len(second_call_messages) == 1, (
            f"Bug: second call received {len(second_call_messages)} messages. "
            "The assistant reply from call 1 leaked into call 2 via list mutation."
        )
        assert request.messages is not None and len(request.messages) == 1, (
            f"Bug: request.messages ended up with {len(request.messages) if request.messages else 0} items after 2 calls. "
            "Expected 1 — the original user message must never be modified."
        )

# ============================================================================
# LLM-OLLA-EDGE-005: OllamaClient.chat() returns response with messages as None 
# when called with minimal input
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_response_messages_is_not_none():
    """LLM-OLLA-EDGE-005: OllamaClient.chat() returns response with messages as None

    This test enforces that OllamaClient.chat() must always return a response
    with response.messages as a non-None value.

    Steps:

    1. Mock the Ollama AsyncClient so that response.message is None
       (simulating the API returning a response object with no message body).
    2. Call OllamaClient.chat() with a minimal valid request
       (a single user message).
    3. Inspect the returned LLMResponse.

    Expected Behavior:

    1. The client does NOT raise an AttributeError (no crash on None.content).
    2. response.messages is not None — the implementation must guard against
       a None message and return a safe, non-None messages list.
    """
    fake_message = AsyncMock()
    fake_message.content = "test"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = None  # Simulate a response where message is None, which should not happen

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

        response = await client.chat(request)

        assert response.messages is not None, (
            "OllamaClient.chat() returned response.messages=None. "
            "This must be fixed in the implementation."
        )

# ============================================================================
# LLM-OLLA-EDGE-006: OllamaClient.chat() handles tool_calls with unexpected type
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_calls_unexpected_type():
    """LLM-OLLA-EDGE-006: OllamaClient.chat() handles tool_calls with unexpected type

    If message.tool_calls is not a list (e.g., a dict or string), the client should handle gracefully.
    Steps:

    1. Mock Ollama response so message.tool_calls is a dict (not a list).
    2. Call OllamaClient.chat() with a valid request.

    Expected Behavior:

    1. The client does not crash.
    2. response.tool_calls is an empty list or handled gracefully.
    """
    fake_message = AsyncMock()
    fake_message.content = "test"
    fake_message.tool_calls = {"function": {"name": "bad_type"}}  # Not a list

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

        response = await client.chat(request)

        # Should not crash, should treat as no tool calls
        assert isinstance(response.tool_calls, list)

# ============================================================================
# LLM-OLLA-EDGE-007: OllamaClient.chat() handles tool_call missing required fields
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_tool_call_missing_fields():
    """LLM-OLLA-EDGE-007: OllamaClient.chat() handles tool_call missing required fields

    If a tool call is missing required fields, the client should not crash.
    Steps:

    1. Mock Ollama response so a tool call is missing required fields (e.g., function.name).
    2. Call OllamaClient.chat() with a valid request.

    Expected Behavior:

    1. The client does not crash.
    2. The response is still marked as successful, and missing fields are handled gracefully.
    """
    mock_tool_call = AsyncMock()
    # Missing function.name and function.arguments
    mock_tool_call.function = AsyncMock()
    del mock_tool_call.function.name
    del mock_tool_call.function.arguments

    fake_message = AsyncMock()
    fake_message.content = ""
    fake_message.tool_calls = [mock_tool_call]

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        response = await client.chat(request)

        # Should not crash, should handle missing fields gracefully
        assert response.success is True

# ============================================================================
# LLM-OLLA-EDGE-008: OllamaClient.chat() handles request with messages=None
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_request_messages_none():
    """LLM-OLLA-EDGE-008: OllamaClient.chat() handles request with messages=None

    If request.messages is None, the client should handle gracefully and not crash.
    Steps:

    1. Create an LLMRequest with messages=None.
    2. Mock Ollama response with a valid message.
    3. Call OllamaClient.chat().

    Expected Behavior:

    1. The client does not crash.
    2. The response contains only the assistant reply in response.messages.
    """
    fake_message = AsyncMock()
    fake_message.content = "reply"
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=None)

        response = await client.chat(request)

        assert response.success is True
        assert response.messages is not None
        assert len(response.messages) == 1  # Only assistant reply

# ============================================================================
# LLM-OLLA-EDGE-009: OllamaClient.chat() handles message.content as unexpected type
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_unexpected_content_type():
    """LLM-OLLA-EDGE-009: OllamaClient.chat() handles message.content as unexpected type

    If message.content is not a string (e.g., a dict), the client should handle gracefully.
    Steps:

    1. Mock Ollama response so message.content is a dict (not a string).
    2. Call OllamaClient.chat() with a valid request.

    Expected Behavior:

    1. The client does not crash.
    2. response.content is converted to a string or set to an empty string.
    """
    fake_message = AsyncMock()
    fake_message.content = {"unexpected": "dict"}
    fake_message.tool_calls = None

    fake_response = AsyncMock()
    fake_response.message = fake_message

    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(return_value=fake_response)

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        response = await client.chat(request)

        # Should not crash, should convert to string or empty string
        assert isinstance(response.content, str)

# ============================================================================
# LLM-OLLA-EDGE-010: OllamaClient.chat() does not retry on unexpected exceptions
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_unexpected_exception_not_retried():
    """LLM-OLLA-EDGE-010: OllamaClient.chat() does not retry on unexpected exceptions

    If an unexpected exception is raised, it should not be retried or swallowed.
    Steps:

    1. Mock Ollama client to raise a RuntimeError on chat.
    2. Call OllamaClient.chat() with a valid request.

    Expected Behavior:

    1. The exception is raised immediately.
    2. The client does not retry the call.
    """
    with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_client:
        instance = mock_client.return_value
        instance.chat = AsyncMock(side_effect=RuntimeError("Unexpected error"))

        client = OllamaClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        with pytest.raises(RuntimeError):
            await client.chat(request)

        # Only one call should be made, no retries
        assert instance.chat.call_count == 1
# ============================================================================
# LLM-OLLA-GSI-001: Google Sheets Integration Verification
# ============================================================================
@pytest.mark.unit
def test_google_sheets_integration_verification():
    """LLM-OLLA-GSI-001: Google Sheets Integration Verification

    Verify that LLM test results are properly recorded in Google Sheets.

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
            creds_file,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id)

        # Check Summary sheet exists
        summary_sheet = sheet.worksheet('Summary')
        summary_data = summary_sheet.get_all_values()

        # The pytest_google_sheets.py plugin writes test results here after every run.
        # Row 0 is the header row, so we need at least 2 rows to confirm data was actually written.
        assert len(summary_data) > 1, "Summary sheet should have data"

        # summary_data[0] is the first row — the column headers the plugin creates
        headers = summary_data[0]
        # These four columns are the core metrics the plugin must write after each test run
        assert 'timestamp' in headers
        assert 'total_tests' in headers
        assert 'passed' in headers
        assert 'failed' in headers

        # Check LLM Integration Testing worksheet (optional - may not exist yet)
        try:
            llm_sheet = sheet.worksheet('LLM Integration Testing')
            llm_data = llm_sheet.get_all_values()

            if llm_data:
                # The automation_status column tracks which test cases are covered by automated tests
                headers = llm_data[0]
                has_automation_status = any('automation' in h.lower() for h in headers)
                assert has_automation_status, "Should have automation_status column"
        except gspread.exceptions.WorksheetNotFound:
            # Worksheet doesn't exist yet - skip this check
            pass

        print("✓ Google Sheets integration verified successfully for LLM tests")

    except Exception as e:
        pytest.fail(f"Google Sheets verification failed: {e}")
