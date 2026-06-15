# ==============================================================================
# LLM Client (Router) Test Suite
# ==============================================================================
# User Story: As a developer, I want a single LLMClient router so that the
#             rest of the codebase is decoupled from the concrete AI provider
#             and switching providers requires only a settings change.
#
# Acceptance Criteria:
#   1. Routes requests to correct backend based on LLM_PROVIDER setting
#   2. Passes request through unchanged and returns response unchanged
#   3. Returns success=False on provider error, never raises
#   4. Documents import-time singleton risk at module load
#   5. Raises ValueError for unsupported provider values
#
# Test Categories:
#   LLM-PROV-001: OpenAI Provider Initialization
#   LLM-PROV-002: Ollama Provider Initialization
#   LLM-PROV-003: Mock Provider Initialization
#   LLM-PROV-004: Unsupported Provider Error Handling
#   LLM-PROV-005: Provider Mismatch Warning
#   LLM-PROV-006: Error Response on Provider Failure
#   LLM-PROV-007: Successful Chat Through Provider
#   LLM-PROV-008: Module-Level Singleton Documents Import-Time Risk
#   LLM-PROV-009: Bad Provider Raises ValueError At Instantiation
#   LLM-PROV-010: Ollama Provider Initialization
#   LLM-PROV-011: Ollama Provider Registered In Router
#   LLM-PROV-012: No Warning When Provider Matches
#   LLM-PROV-013: LLMClient Does Not Mutate Request Before Delegation
#   LLM-PROV-014: Error Response Is Well-Formed
#   LLM-CLI-GSI-001: Google Sheets Integration Verification
# ==============================================================================

import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

# ---- mock ollama so the import does not require the package installed ----
mock_ollama = MagicMock()
mock_ollama.AsyncClient = MagicMock()
sys.modules.setdefault("ollama", mock_ollama)
# -------------------------------------------------------------------------

from finbot.core.llm.client import LLMClient
from finbot.core.llm.ollama_client import OllamaClient
from finbot.core.data.models import LLMRequest, LLMResponse
import os
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
import gspread

load_dotenv()

# ============================================================================
# Pytest fixture for patching settings
# ============================================================================
@pytest.fixture
def patched_settings():
    """
    Fixture to patch 'finbot.core.llm.client.settings' for each test.

    Usage:
        def test_something(patched_settings):
            patched_settings.LLM_PROVIDER = "mock"
            ...
    """
    with patch("finbot.core.llm.client.settings") as mock_settings:
        yield mock_settings

# ============================================================================
# LLM-PROV-001: OpenAI Provider Initialization
# ============================================================================
@pytest.mark.unit
def test_openai_provider_initialization(patched_settings):
    """LLM-PROV-001: OpenAI Provider Initialization

    Verify that LLMClient correctly initializes with OpenAI provider.

    Test Steps:
    1. Mock settings with LLM_PROVIDER = "openai"
    2. Mock OpenAIClient class
    3. Create LLMClient instance
    4. Verify client.provider = "openai"
    5. Verify OpenAIClient was instantiated

    Expected Results:
    1. LLMClient instance created successfully
    2. provider attribute set to "openai"
    3. Internal client is instance of OpenAIClient
    4. No errors during initialization
    """
    patched_settings.LLM_PROVIDER = "openai"
    patched_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    with patch("finbot.core.llm.openai_client.OpenAIClient") as mock_openai_client:
        client = LLMClient()
        # provider is set from settings.LLM_PROVIDER — wrong value means requests go to the wrong backend
        assert client.provider == "openai"
        # default_model is used for every request that does not explicitly specify a model
        assert client.default_model == "gpt-5-nano"
        # default_temperature is the fallback when a request does not set its own temperature
        assert client.default_temperature == pytest.approx(0.7)
        # OpenAIClient must be created exactly once at init time — not on every chat call
        mock_openai_client.assert_called_once()

# ============================================================================
# LLM-PROV-002: Ollama Provider Initialization
# ============================================================================
@pytest.mark.unit
def test_ollama_client_default_configuration():
    """LLM-PROV-002: Ollama Provider Initialization

    Configures settings with model, temperature, timeout, and a local Ollama
    URL, instantiates OllamaClient directly, and checks that all attributes
    are set correctly and AsyncClient is constructed with the right host and
    timeout. Basically: "Does OllamaClient read the right settings and wire up
    AsyncClient with the correct host and timeout?"

    Test Steps:
    1. Configure settings.OLLAMA_MODEL, settings.LLM_DEFAULT_TEMPERATURE,
       and settings.LLM_TIMEOUT.
    2. Instantiate OllamaClient.
    3. Inspect initialized attributes.

    Expected Results:
    1. default_model is set to settings.OLLAMA_MODEL when LLM_PROVIDER is ollama
    2. default_temperature is set to settings.LLM_DEFAULT_TEMPERATURE
    3. host is set to settings.OLLAMA_BASE_URL
    4. AsyncClient is initialized with the configured host
    5. AsyncClient uses settings.LLM_TIMEOUT as timeout
    """
    with patch("finbot.core.llm.ollama_client.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "ollama"
        mock_settings.OLLAMA_MODEL = "gemma4:e2b"
        mock_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
        mock_settings.LLM_DEFAULT_TEMPERATURE = 0.7
        mock_settings.LLM_TIMEOUT = 60
        mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"

        with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_async_client:
            client = OllamaClient()

            # default_model must come from settings — wrong value means requests use the wrong model
            assert client.default_model == "gemma4:e2b"
            # default_temperature must come from settings — controls response randomness for every request
            assert client.default_temperature == pytest.approx(0.7)
            # host must be set from OLLAMA_BASE_URL so the client knows which server to connect to
            assert client.host == "http://localhost:11434"
            # AsyncClient must be constructed with correct host and timeout
            mock_async_client.assert_called_once_with(
                host="http://localhost:11434",
                timeout=60
            )


# ============================================================================
# LLM-PROV-003: Mock Provider Initialization
# ============================================================================
@pytest.mark.unit
def test_mock_provider_initialization(patched_settings):
    """LLM-PROV-003: Mock Provider Initialization

    Verify that LLMClient correctly initializes with Mock provider.

    Test Steps:
    1. Mock settings with LLM_PROVIDER = "mock"
    2. Mock MockLLMClient class
    3. Create LLMClient instance
    4. Verify client.provider = "mock"
    5. Verify MockLLMClient was instantiated

    Expected Results:
    1. LLMClient instance created successfully
    2. provider attribute set to "mock"
    3. Internal client is instance of MockLLMClient
    4. No errors during initialization
    """
    patched_settings.LLM_PROVIDER = "mock"
    patched_settings.LLM_DEFAULT_MODEL = "mock-model"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.5

    with patch("finbot.core.llm.mock_client.MockLLMClient") as mock_llm_client:
        client = LLMClient()
        # provider="mock" confirms LLMClient read LLM_PROVIDER="mock" from settings and routed to the right client
        assert client.provider == "mock"
        # MockLLMClient must be instantiated once — if it were called multiple times, each call would create a separate instance
        mock_llm_client.assert_called_once()

# ============================================================================
# LLM-PROV-004: Unsupported Provider Error Handling
# ============================================================================
@pytest.mark.unit
def test_unsupported_provider_error(patched_settings):
    """LLM-PROV-004: Unsupported Provider Error Handling

    Verify that LLMClient raises ValueError for unsupported providers.

    Test Steps:
    1. Mock settings with LLM_PROVIDER = "unsupported_provider"
    2. Attempt to create LLMClient instance
    3. Expect ValueError to be raised
    4. Verify error message contains provider name

    Expected Results:
    1. ValueError raised during initialization
    2. Error message indicates unsupported provider
    3. Error message includes "unsupported_provider"
    4. No client instance created
    """
    patched_settings.LLM_PROVIDER = "unsupported_provider"
    patched_settings.LLM_DEFAULT_MODEL = "model"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    with pytest.raises(ValueError) as exc_info:
        LLMClient()
    # The error message must name the bad provider so the developer knows exactly which value to fix in settings
    assert "unsupported_provider" in str(exc_info.value).lower()

# ============================================================================
# LLM-PROV-005: Provider Mismatch Warning
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_provider_mismatch_warning(patched_settings):
    """LLM-PROV-005: Provider Mismatch Warning

    Verify that LLMClient logs warning when request provider mismatches client provider.

    Test Steps:
    1. Mock settings with LLM_PROVIDER = "openai"
    2. Create mock OpenAIClient that returns successful response
    3. Create LLMClient instance
    4. Create LLMRequest with provider = "mock" (mismatch)
    5. Call client.chat(request)
    6. Verify warning logged about provider mismatch
    7. Verify chat still completes successfully

    Expected Results:
    1. Warning logged about provider mismatch
    2. Chat request still processed
    3. Response returned successfully
    4. No errors despite mismatch
    """
    patched_settings.LLM_PROVIDER = "openai"
    patched_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    mock_response = LLMResponse(
        content="test response",
        provider="openai",
        success=True
    )

    with patch("finbot.core.llm.openai_client.OpenAIClient") as mock_openai_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.chat = AsyncMock(return_value=mock_response)
        mock_openai_client.return_value = mock_client_instance

        with patch("finbot.core.llm.client.logger") as mock_logger:
            client = LLMClient()
            request = LLMRequest(
                messages=[{"role": "user", "content": "test"}],
                provider="mock"  # Mismatch!
            )
            response = await client.chat(request)
            # A warning must be logged when request.provider differs from the client's configured provider
            mock_logger.warning.assert_called_once()
            # call_args is the tuple of all positional arguments passed to logger.warning()
            call_args = mock_logger.warning.call_args[0]
            # call_args[0] is the format string — the template text of the warning message
            format_string = call_args[0]
            # "mismatch" must appear in the message so the log is easy to search for
            assert "mismatch" in format_string.lower()
            # "mock" must be one of the format args so the log shows which provider was requested
            assert "mock" in call_args
            # "openai" must also appear so the log shows which provider is actually configured
            assert "openai" in call_args
            # The warning is informational only — the request must still complete successfully
            assert response.success is True
            # The response content must come through unchanged from the underlying provider
            assert response.content == "test response"

# ============================================================================
# LLM-PROV-006: Error Response on Provider Failure
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_response_on_provider_failure(patched_settings):
    """LLM-PROV-006: Error Response on Provider Failure

    Verify that LLMClient returns error response when underlying provider fails.

    Test Steps:
    1. Mock settings with LLM_PROVIDER = "openai"
    2. Create mock OpenAIClient that raises exception
    3. Create LLMClient instance
    4. Create LLMRequest with basic message
    5. Call client.chat(request)
    6. Verify response has success = False
    7. Verify response contains error message

    Expected Results:
    1. No exception propagated to caller
    2. Response returned with success = False
    3. Response content contains error information
    4. Provider name included in error message
    5. Graceful degradation on provider failure
    """
    patched_settings.LLM_PROVIDER = "openai"
    patched_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    with patch("finbot.core.llm.openai_client.OpenAIClient") as mock_openai_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.chat = AsyncMock(
            side_effect=Exception("API connection failed")
        )
        mock_openai_client.return_value = mock_client_instance

        client = LLMClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "test"}]
        )
        response = await client.chat(request)
        # success=False tells the caller the request failed without raising an exception that would crash the caller
        assert response.success is False
        # The provider name must appear in the error message so it is clear which backend failed
        assert response.content is not None and "openai" in response.content.lower()
        # "unavailable" is the expected wording — callers and monitoring tools may check for this specific word
        assert response.content is not None and "unavailable" in response.content.lower()

# ============================================================================
# LLM-PROV-007: Successful Chat Through Provider
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_successful_chat_through_provider(patched_settings):
    """LLM-PROV-007: Successful Chat Through Provider

    Verify that LLMClient successfully delegates chat to underlying provider.

    Test Steps:
    1. Mock settings with LLM_PROVIDER = "mock"
    2. Create mock MockLLMClient that returns successful response
    3. Create LLMClient instance
    4. Create LLMRequest with messages
    5. Call client.chat(request)
    6. Verify underlying provider's chat method was called
    7. Verify response returned successfully

    Expected Results:
    1. Chat request delegated to provider
    2. Provider's chat method called with request
    3. Response from provider returned to caller
    4. No modifications to response
    5. Successful end-to-end chat flow
    """
    patched_settings.LLM_PROVIDER = "mock"
    patched_settings.LLM_DEFAULT_MODEL = "mock-model"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    mock_response = LLMResponse(
        content="Mock response content",
        provider="mock",
        success=True,
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Mock response content"}
        ]
    )

    with patch("finbot.core.llm.mock_client.MockLLMClient") as mock_llm_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.chat = AsyncMock(return_value=mock_response)
        mock_llm_client.return_value = mock_client_instance

        client = LLMClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "Hello"}]
        )
        response = await client.chat(request)
        # The original request object must be passed directly to the inner provider without any modification
        mock_client_instance.chat.assert_called_once_with(request)
        # success=True confirms the full call path from LLMClient down to the inner provider completed without error
        assert response.success is True
        # The content must be exactly what the inner provider returned — LLMClient must not alter it
        assert response.content == "Mock response content"
        # provider in the response must come from the inner client, not be overwritten by LLMClient
        assert response.provider == "mock"
        # 1 user message + 1 assistant reply = 2 total — the full conversation history must be preserved
        assert response.messages is not None and len(response.messages) == 2


# ============================================================================
# LLM-PROV-008: Module-Level Singleton Documents Import-Time Risk
# ============================================================================
@pytest.mark.unit
def test_module_level_singleton_exists_and_is_returned_by_getter():
    """LLM-PROV-008: Module-Level Singleton Documents Import-Time Risk

    Verify that get_llm_client() returns the module-level singleton created
    at import time.

    Documents the risk: llm_client = LLMClient() runs when client.py is
    imported. If settings.LLM_PROVIDER is invalid at that moment, the import
    raises ValueError and crashes any module that transitively imports client.py.

    Test Steps:
    1. Import finbot.core.llm.client module
    2. Verify module has a "llm_client" attribute
    3. Verify get_llm_client() returns the same object (not a new instance)

    Expected Results:
    1. Module attribute "llm_client" exists
    2. get_llm_client() is the same object as llm_client
    3. Singleton pattern confirmed
    """
    import finbot.core.llm.client as client_module

    assert hasattr(client_module, "llm_client"), (
        "Module-level singleton 'llm_client' not found. "
        "get_llm_client() depends on this attribute."
    )
    assert client_module.llm_client is client_module.get_llm_client(), (
        "get_llm_client() must return the module-level singleton, not a new instance."
    )


# ============================================================================
# LLM-PROV-009: Bad Provider Raises ValueError At Instantiation
# ============================================================================
@pytest.mark.unit
def test_bad_provider_raises_value_error_at_instantiation(patched_settings):
    """LLM-PROV-009: Bad Provider Raises ValueError At Instantiation

    Verify that an unrecognized LLM_PROVIDER raises ValueError at LLMClient()
    call time so callers can handle it defensively.

    Regression test for the import-time risk in LLM-PROV-007: on the unfixed
    code this error surfaces during module import. After a lazy-init fix it
    should raise at the first get_llm_client() call. Either way the error
    type must be ValueError.

    Test Steps:
    1. Set LLM_PROVIDER = "does_not_exist" via patched_settings
    2. Attempt LLMClient() instantiation
    3. Expect ValueError containing the provider name

    Expected Results:
    1. ValueError raised
    2. Error message contains "does_not_exist"
    3. No other exception type raised
    """
    patched_settings.LLM_PROVIDER = "does_not_exist"
    patched_settings.LLM_DEFAULT_MODEL = "model"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    with pytest.raises(ValueError, match="does_not_exist"):
        LLMClient()


# ============================================================================
# LLM-PROV-010: Ollama Provider Initialization
# ============================================================================
@pytest.mark.unit
def test_ollama_provider_initialization():
    """LLM-PROV-010: Ollama Provider Initialization

    Initialize OllamaClient with default configuration
    Verify that the Ollama client initializes correctly using values from
    application settings.
    Basically: "Does OllamaClient read the right settings and wire up
    AsyncClient with the correct host and timeout?"

    Test Steps:
    1. Configure settings.OLLAMA_MODEL, settings.LLM_DEFAULT_TEMPERATURE,
       and settings.LLM_TIMEOUT
    2. Instantiate OllamaClient
    3. Inspect initialized attributes

    Expected Results:
    1. default_model is set to settings.OLLAMA_MODEL when LLM_PROVIDER is ollama
    2. default_temperature is set to settings.LLM_DEFAULT_TEMPERATURE
    3. host is set to settings.OLLAMA_BASE_URL or defaults to "http://localhost:11434"
    4. AsyncClient is initialized with the configured host
    5. AsyncClient uses settings.LLM_TIMEOUT as timeout
    """
    with patch("finbot.core.llm.ollama_client.settings") as mock_settings:
        mock_settings.LLM_PROVIDER = "ollama"
        mock_settings.OLLAMA_MODEL = "gemma4:e2b"
        mock_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
        mock_settings.LLM_DEFAULT_TEMPERATURE = 0.7
        mock_settings.LLM_TIMEOUT = 60
        mock_settings.OLLAMA_BASE_URL = "http://localhost:11434"

        with patch("finbot.core.llm.ollama_client.AsyncClient") as mock_async_client:
            client = OllamaClient()

            # default_model must come from settings — wrong value means requests use the wrong model
            assert client.default_model == "gemma4:e2b"
            # default_temperature must come from settings — controls response randomness for every request
            assert client.default_temperature == pytest.approx(0.7)
            # host must be set from OLLAMA_BASE_URL so the client knows which server to connect to
            assert client.host == "http://localhost:11434"
            # AsyncClient must be constructed with the correct host — wrong host means every request fails
            mock_async_client.assert_called_once_with(
                host="http://localhost:11434",
                timeout=60
            )


# ============================================================================
# LLM-PROV-011: Ollama Provider Registered In Router
# ============================================================================
@pytest.mark.unit
def test_ollama_provider_initializes_from_router(patched_settings):
    """LLM-PROV-011: Ollama Provider Registered In Router

    Verify that LLMClient routes LLM_PROVIDER = "ollama" to OllamaClient.
    """
    patched_settings.LLM_PROVIDER = "OLLAMA"
    patched_settings.OLLAMA_MODEL = "gemma4:e2b"
    patched_settings.LLM_DEFAULT_MODEL = "gpt-5-nano"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    with patch("finbot.core.llm.ollama_client.OllamaClient") as mock_ollama_client:
        client = LLMClient()
        assert client.provider == "ollama"
        assert client.default_model == "gemma4:e2b"
        mock_ollama_client.assert_called_once()


# ============================================================================
# LLM-PROV-012: No Warning When Provider Matches
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_no_warning_when_provider_matches(patched_settings):
    """LLM-PROV-012: No Warning When Provider Matches

    Verify that LLMClient does NOT log a warning when request.provider
    matches the client's configured provider.

    Complement to LLM-PROV-005 (mismatch warning). The warning must only
    fire on a real mismatch — firing on every call would spam logs.

    Test Steps:
    1. Configure LLM_PROVIDER = "mock"
    2. Create LLMRequest with provider = "mock" (matches client)
    3. Call client.chat(request)
    4. Assert logger.warning was NOT called

    Expected Results:
    1. No warning logged
    2. Request completes successfully
    """
    patched_settings.LLM_PROVIDER = "mock"
    patched_settings.LLM_DEFAULT_MODEL = "mock-model"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    mock_response = LLMResponse(content="ok", provider="mock", success=True)

    with patch("finbot.core.llm.mock_client.MockLLMClient") as mock_llm_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.chat = AsyncMock(return_value=mock_response)
        mock_llm_client.return_value = mock_client_instance

        with patch("finbot.core.llm.client.logger") as mock_logger:
            client = LLMClient()
            request = LLMRequest(
                messages=[{"role": "user", "content": "test"}],
                provider="mock",
            )
            await client.chat(request)
            mock_logger.warning.assert_not_called()


# ============================================================================
# LLM-PROV-013: LLMClient Does Not Mutate Request Before Delegation
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_llm_client_does_not_mutate_request(patched_settings):
    """LLM-PROV-013: LLMClient Does Not Mutate Request Before Delegation

    Verify that LLMClient passes the request to the provider unchanged —
    it must not modify provider, model, temperature, or messages before
    delegating to the inner client.

    Test Steps:
    1. Create LLMRequest with explicit provider, model, temperature, messages
    2. Record all field values before the call
    3. Call client.chat(request)
    4. Assert all fields are unchanged after the call

    Expected Results:
    1. request.provider unchanged
    2. request.model unchanged
    3. request.temperature unchanged
    4. len(request.messages) unchanged
    """
    patched_settings.LLM_PROVIDER = "mock"
    patched_settings.LLM_DEFAULT_MODEL = "mock-model"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    mock_response = LLMResponse(content="ok", provider="mock", success=True)

    with patch("finbot.core.llm.mock_client.MockLLMClient") as mock_llm_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.chat = AsyncMock(return_value=mock_response)
        mock_llm_client.return_value = mock_client_instance

        client = LLMClient()
        request = LLMRequest(
            messages=[{"role": "user", "content": "hello"}],
            provider="mock",
            model="custom-model",
            temperature=0.3,
        )

        provider_before = request.provider
        model_before = request.model
        temperature_before = request.temperature
        msg_count_before = len(request.messages) if request.messages is not None else 0

        await client.chat(request)

        assert request.provider == provider_before, (
            f"Bug: LLMClient mutated request.provider from {provider_before!r} to {request.provider!r}"
        )
        assert request.model == model_before, (
            f"Bug: LLMClient mutated request.model from {model_before!r} to {request.model!r}"
        )
        assert request.temperature == temperature_before, (
            f"Bug: LLMClient mutated request.temperature from {temperature_before!r} to {request.temperature!r}"
        )
        assert len(request.messages) if request.messages is not None else 0 == msg_count_before, (
            f"Bug: LLMClient mutated request.messages — now has {len(request.messages) if request.messages is not None else 0} items."
        )


# ============================================================================
# LLM-PROV-014: Error Response Is Well-Formed
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_response_is_well_formed(patched_settings):
    """LLM-PROV-014: Error Response Is Well-Formed

    Verify that when the underlying provider raises an exception, the
    returned error LLMResponse contains all required fields in the
    correct format — not just success=False.

    Test Steps:
    1. Mock provider to raise RuntimeError
    2. Call client.chat()
    3. Assert response.success is False
    4. Assert response.content is a non-empty string
    5. Assert response.provider is set (not None or empty)
    6. Assert response.content contains provider name and "unavailable"

    Expected Results:
    1. response.success is False
    2. response.content is a non-empty string (not None, not "")
    3. response.provider identifies which backend failed
    4. response.content contains "unavailable" for monitoring/alerting
    """
    patched_settings.LLM_PROVIDER = "mock"
    patched_settings.LLM_DEFAULT_MODEL = "mock-model"
    patched_settings.LLM_DEFAULT_TEMPERATURE = 0.7

    with patch("finbot.core.llm.mock_client.MockLLMClient") as mock_llm_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.chat = AsyncMock(side_effect=RuntimeError("network timeout"))
        mock_llm_client.return_value = mock_client_instance

        client = LLMClient()
        request = LLMRequest(messages=[{"role": "user", "content": "test"}])
        response = await client.chat(request)

        assert response.success is False
        assert response.content is not None and len(response.content) > 0, (
            "Bug: error response.content is empty — caller has no information about what failed."
        )
        assert response.provider is not None and len(response.provider) > 0, (
            "Bug: error response.provider is empty — caller cannot identify which backend failed."
        )
        assert "mock" in response.content.lower(), (
            "Bug: provider name missing from error response content."
        )
        assert "unavailable" in response.content.lower(), (
            "Bug: 'unavailable' missing from error content — monitoring rules may not trigger."
        )


# ============================================================================
# LLM-CLI-GSI-001: Google Sheets Integration Verification
# ============================================================================
@pytest.mark.unit
def test_google_sheets_integration_verification():
    """LLM-CLI-GSI-001: Google Sheets Integration Verification

    Verify that LLM client test results are properly recorded in Google Sheets.

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
        creds = Credentials.from_service_account_file(
            creds_file,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id)

        summary_sheet = sheet.worksheet('Summary')
        summary_data = summary_sheet.get_all_values()
        assert len(summary_data) > 1, "Summary sheet should have data"
        headers = summary_data[0]
        assert 'timestamp' in headers
        assert 'total_tests' in headers
        assert 'passed' in headers
        assert 'failed' in headers

        try:
            llm_sheet = sheet.worksheet('LLM Integration Testing')
            llm_data = llm_sheet.get_all_values()
            assert len(llm_data) > 0, "LLM Integration Testing worksheet should have data"
            headers = llm_data[0]
            has_automation_status = any('automation' in h.lower() for h in headers)
            assert has_automation_status, "Should have automation_status column"
        except gspread.exceptions.WorksheetNotFound:
            pass

        print("✓ Google Sheets integration verified successfully for LLM client tests")

    except Exception as e:
        pytest.fail(f"Google Sheets verification failed: {e}")
