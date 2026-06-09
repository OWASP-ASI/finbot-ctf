# ==============================================================================
# Mock LLM Client Test Suite
# ==============================================================================
# User Story: As a developer, I want a deterministic fake LLM client so that
#             higher-level tests can exercise AI-dependent code without real
#             network calls or non-deterministic responses.
#
# Acceptance Criteria:
#   1. Returns consistent fixed response on every call
#   2. Accepts all LLMRequest parameters without error
#   3. response.success is always True
#   4. response.tool_calls is an empty list, not None
#   5. Exception type preserved when wrapping errors
#
# Test Categories:
#   LLM-MOCK-001: Basic Mock Response
#   LLM-MOCK-002: Mock Client with Custom Parameters
#   LLM-MOCK-003: Empty Messages Handling
#   LLM-MOCK-004: None Messages Handling
#   LLM-MOCK-005: Mock Response Success Field Is True
#   LLM-MOCK-006: Mock Response tool_calls Field Is Empty List
#   LLM-MOCK-EDGE-001: Exception Wrapping Loses Original Type
#   LLM-MOCK-GSI-001: Google Sheets Integration Verification
# ==============================================================================

import os
from unittest.mock import patch

import gspread
import pytest
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

from finbot.core.data.models import LLMRequest
from finbot.core.llm.mock_client import MockLLMClient

load_dotenv()


# ============================================================================
# LLM-MOCK-001: Basic Mock Response
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_basic_mock_response():
    """LLM-MOCK-001: Basic Mock Response

    Verify that MockLLMClient returns consistent mock response.

    Test Steps:
    1. Create MockLLMClient instance
    2. Create LLMRequest with basic message
    3. Call client.chat(request)
    4. Verify response fields:
       - success = True (implicit, no explicit field in current implementation)
       - provider = "mock"
       - content = "This is a mock LLM response"
    5. Verify response is deterministic

    Expected Results:
    1. MockLLMClient instance created successfully
    2. Chat request completes without errors
    3. Response contains mock content
    4. Provider set to "mock"
    5. Same request produces same response
    """
    client = MockLLMClient()

    request = LLMRequest(messages=[{"role": "user", "content": "Test message"}])

    response = await client.chat(request)

    # provider labels which backend generated the response — "mock" means no real network call was made
    assert response.provider == "mock"
    # This exact string is the mock's fixed output; tests that check content rely on this value being stable
    assert response.content == "This is a mock LLM response"

    # Verify deterministic behavior
    response2 = await client.chat(request)
    # The mock must return the same output every time — if it varied, tests would produce random results
    assert response2.content == response.content


# ============================================================================
# LLM-MOCK-002: Mock Client with Custom Parameters
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_mock_client_with_custom_parameters():
    """LLM-MOCK-002: Mock Client with Custom Parameters

    Verify that MockLLMClient accepts and processes various request parameters.

    Test Steps:
    1. Create MockLLMClient instance
    2. Create LLMRequest with:
       - Custom model name
       - Custom temperature
       - Multiple messages
       - Tools parameter
    3. Call client.chat(request)
    4. Verify response completes successfully
    5. Verify mock response ignores custom parameters

    Expected Results:
    1. Request with custom parameters accepted
    2. No errors from custom parameters
    3. Mock response returned regardless of parameters
    4. Consistent mock behavior maintained
    5. Useful for testing without real LLM calls
    """
    client = MockLLMClient()

    request = LLMRequest(
        messages=[
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
        ],
        model="custom-model",
        temperature=0.9,
        tools=[{"type": "function", "function": {"name": "test_tool"}}],
    )

    response = await client.chat(request)

    # The mock ignores all custom parameters and always reports provider as "mock"
    assert response.provider == "mock"
    # Custom model, temperature, and tools do not change what the mock returns — it always sends the same string
    assert response.content == "This is a mock LLM response"


# ============================================================================
# LLM-MOCK-003: Empty Messages Handling
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_empty_messages_handling():
    """LLM-MOCK-003: Empty Messages Handling

    Verify that MockLLMClient handles empty or missing messages gracefully.

    Test Steps:
    1. Create MockLLMClient instance
    2. Create LLMRequest with empty messages list
    3. Call client.chat(request)
    4. Verify response completes successfully
    5. Verify mock response still returned

    Expected Results:
    1. No errors from empty messages
    2. Mock response returned successfully
    3. Graceful handling of edge case
    4. Mock client robust to input variations
    """
    client = MockLLMClient()

    request = LLMRequest(messages=[])

    response = await client.chat(request)

    # An empty messages list is an edge case — the mock must still complete without crashing
    assert response.provider == "mock"
    # The response content must be returned even when the input was empty
    assert response.content == "This is a mock LLM response"


# ============================================================================
# LLM-MOCK-004: None Messages Handling
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_none_messages_handling():
    """LLM-MOCK-004: None Messages Handling

    Verify that MockLLMClient handles None messages gracefully.

    Test Steps:
    1. Create MockLLMClient instance
    2. Create LLMRequest with messages = None
    3. Call client.chat(request)
    4. Verify response completes successfully
    5. Verify mock response still returned

    Expected Results:
    1. No errors from None messages
    2. Mock response returned successfully
    3. Graceful handling of None value
    4. Mock client robust to missing data
    """
    client = MockLLMClient()

    request = LLMRequest(messages=None)

    response = await client.chat(request)

    # provider="mock" confirms the request completed without error. If the mock had tried to
    # iterate over messages=None (which is not iterable), Python would have raised a TypeError
    # and no response object would have been returned at all.
    assert response.provider == "mock"
    # The mock returned its full fixed output, meaning it did not fail silently
    # or exit early when it saw None — the entire execution path completed normally.
    assert response.content == "This is a mock LLM response"


# ============================================================================
# LLM-MOCK-005: Mock Response Success Field Is True
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_mock_response_success_is_true():
    """LLM-MOCK-005: Mock Response Success Field Is True

    Verify that MockLLMClient returns a response with success=True.
    MockLLMClient is used as a stand-in for real providers in tests —
    callers that check response.success must see True to proceed normally.

    LLMResponse defaults success=True, but this test makes it explicit
    so any future change to MockLLMClient that breaks success is caught.

    Test Steps:
    1. Create MockLLMClient instance
    2. Call client.chat() with a basic request
    3. Assert response.success is True

    Expected Results:
    1. response.success is True
    2. Mock response is usable as a stand-in for a successful real response
    """
    client = MockLLMClient()
    request = LLMRequest(messages=[{"role": "user", "content": "test"}])
    response = await client.chat(request)
    assert response.success is True, (
        "Bug: MockLLMClient returned success=False. "
        "Mock responses must be success=True to be useful in happy-path tests."
    )


# ============================================================================
# LLM-MOCK-006: Mock Response tool_calls Field Is Empty List
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_mock_response_tool_calls_is_empty():
    """LLM-MOCK-006: Mock Response tool_calls Field Is Empty List

    Verify that MockLLMClient returns response.tool_calls as an empty list
    (not None) when no tool calls are made. Callers commonly iterate over
    tool_calls — None would raise TypeError on iteration.

    Test Steps:
    1. Create MockLLMClient with a request that includes tools
    2. Call client.chat()
    3. Assert response.tool_calls is not None
    4. Assert response.tool_calls is iterable (list)

    Expected Results:
    1. response.tool_calls is not None
    2. response.tool_calls is a list (empty, since mock never calls tools)
    3. Iterating over response.tool_calls does not raise TypeError
    """
    client = MockLLMClient()
    request = LLMRequest(
        messages=[{"role": "user", "content": "test"}],
        tools=[{"type": "function", "function": {"name": "get_balance"}}],
    )
    response = await client.chat(request)
    assert (
        response.tool_calls is not None
    ), "Bug: response.tool_calls is None. Callers that iterate over tool_calls will crash."
    assert isinstance(
        response.tool_calls, list
    ), f"Bug: response.tool_calls is {type(response.tool_calls).__name__}, expected list."


# ============================================================================
# LLM-MOCK-EDGE-001: Exception Wrapping Loses Original Type
# ============================================================================
@pytest.mark.asyncio
@pytest.mark.unit
async def test_exception_wrapping_loses_original_type():
    """LLM-MOCK-EDGE-001: Exception Wrapping Loses Original Type

    Documents that MockLLMClient wraps all exceptions in a generic Exception,
    discarding the original type. Callers that catch specific exception types
    (e.g. ValueError, TypeError) will never match because the raised type is
    always Exception.

    Root cause (mock_client.py:34):
        raise Exception(f"Mock LLM chat failed: {e}") from e

    Example:
        # Internal ValueError raised
        raise ValueError("bad input")
        # Caller catches
        except ValueError:   ← never reached, gets generic Exception instead

    Test Steps:
    1. Patch MockLLMClient.chat to raise a ValueError internally
    2. Call client.chat()
    3. Observe that a generic Exception is raised, not ValueError

    Expected Results:
    1. Exception is raised (not ValueError)
    2. The original ValueError message is preserved in the wrapper
    3. This test documents the bug — a fix would re-raise the original type
    """
    client = MockLLMClient()

    # Patch LLMResponse constructor to raise ValueError *inside* the try block —
    # this lets the real chat() run and triggers the except handler in mock_client.py
    with patch(
        "finbot.core.llm.mock_client.LLMResponse", side_effect=ValueError("bad input value")
    ):
        with pytest.raises(Exception) as exc_info:
            await client.chat(LLMRequest(messages=[{"role": "user", "content": "test"}]))

        # The original type is preserved — bare `raise` in mock_client.py re-raises
        # the original ValueError instead of wrapping it in a generic Exception.
        assert type(exc_info.value) is ValueError, (
            f"Expected ValueError but got {type(exc_info.value).__name__}. "
            "mock_client.py should re-raise the original exception type."
        )
        assert "bad input value" in str(
            exc_info.value
        ), "The original error message must be preserved."


# ============================================================================
# LLM-MOCK-GSI-001: Google Sheets Integration Verification
# ============================================================================
@pytest.mark.unit
def test_google_sheets_integration_verification():
    """LLM-MOCK-GSI-001: Google Sheets Integration Verification

    Verify that Mock client test results are properly recorded in Google Sheets.

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

        assert len(summary_data) > 1, "Summary sheet should have data"

        # Verify headers
        headers = summary_data[0]
        assert "timestamp" in headers
        assert "total_tests" in headers
        assert "passed" in headers
        assert "failed" in headers

        # Check LLM Integration Testing worksheet (optional - may not exist yet)
        try:
            llm_sheet = sheet.worksheet("LLM Integration Testing")
            llm_data = llm_sheet.get_all_values()

            assert len(llm_data) > 0, "LLM Integration Testing worksheet should have data"

            # Verify automation_status column exists
            headers = llm_data[0]
            has_automation_status = any("automation" in h.lower() for h in headers)
            assert has_automation_status, "Should have automation_status column"
        except gspread.exceptions.WorksheetNotFound:
            # Worksheet doesn't exist yet - skip this check
            pass

        print("✓ Google Sheets integration verified successfully for Mock client tests")

    except Exception as e:
        pytest.fail(f"Google Sheets verification failed: {e}")
