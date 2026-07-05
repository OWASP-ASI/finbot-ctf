"""Tests for finbot.security.mappings."""

import pytest

from finbot.security.mappings import (
    OPERATIONAL_TO_SECURITY_CATEGORY,
    TOOL_OUTPUT_OPERATIONAL_EVENTS,
    TOOL_PARAMETERS_OPERATIONAL_EVENTS,
    build_native_tool_arguments,
    extract_tool_arguments_from_event,
    infer_tool_source_from_event,
    normalize_tool_output,
    normalize_tool_parameters,
    operational_event_action,
    security_category_for_operational_event,
)
from finbot.security.schemas import SecurityEventCategory


class TestOperationalMappings:
    def test_parameters_operational_events(self):
        assert TOOL_PARAMETERS_OPERATIONAL_EVENTS == {
            "tool_call_start",
            "mcp_tool_call_start",
        }

    def test_output_operational_events(self):
        assert "tool_call_success" in TOOL_OUTPUT_OPERATIONAL_EVENTS
        assert "mcp_tool_call_failure" in TOOL_OUTPUT_OPERATIONAL_EVENTS

    def test_operational_to_security_category_complete(self):
        assert len(OPERATIONAL_TO_SECURITY_CATEGORY) == 6
        assert (
            OPERATIONAL_TO_SECURITY_CATEGORY["tool_call_start"]
            == SecurityEventCategory.tool_parameters
        )
        assert (
            OPERATIONAL_TO_SECURITY_CATEGORY["mcp_tool_call_success"]
            == SecurityEventCategory.tool_output
        )

    @pytest.mark.parametrize(
        ("event_type", "expected"),
        [
            ("agent.invoice_agent.tool_call_start", "tool_call_start"),
            ("agent.security.tool_output", "tool_output"),
            ("", ""),
        ],
    )
    def test_operational_event_action(self, event_type: str, expected: str):
        assert operational_event_action(event_type) == expected

    @pytest.mark.parametrize(
        ("event_type", "category"),
        [
            ("agent.foo.mcp_tool_call_start", SecurityEventCategory.tool_parameters),
            ("agent.foo.tool_call_failure", SecurityEventCategory.tool_output),
            ("agent.foo.task_start", None),
        ],
    )
    def test_security_category_for_operational_event(
        self, event_type: str, category: SecurityEventCategory | None
    ):
        assert security_category_for_operational_event(event_type) == category


class TestBuildNativeToolArguments:
    def test_kwargs_only(self):
        assert build_native_tool_arguments(None, {"vendor_id": 1}) == {"vendor_id": 1}

    def test_args_and_kwargs(self):
        result = build_native_tool_arguments([1, "x"], {"flag": True})
        assert result["flag"] is True
        assert result["_positional_args"] == [1, "x"]

    def test_empty(self):
        assert build_native_tool_arguments(None, None) == {}


class TestExtractToolArguments:
    def test_mcp_tool_arguments(self):
        event = {"tool_arguments": {"vendor_id": 5, "limit": 10}}
        assert extract_tool_arguments_from_event(event) == {"vendor_id": 5, "limit": 10}

    def test_chat_arguments(self):
        event = {"arguments": {"query": "invoice"}}
        assert extract_tool_arguments_from_event(event) == {"query": "invoice"}

    def test_native_args_kwargs(self):
        event = {
            "tool_args": [99],
            "tool_kwargs": {"invoice_id": 3},
        }
        assert extract_tool_arguments_from_event(event) == {
            "invoice_id": 3,
            "_positional_args": [99],
        }


class TestInferToolSource:
    def test_mcp_from_event_type(self):
        event = {"event_type": "agent.x.mcp_tool_call_start"}
        assert infer_tool_source_from_event(event) == "mcp"

    def test_chat_subtype(self):
        event = {"event_subtype": "chat", "event_type": "agent.chat.tool_call_start"}
        assert infer_tool_source_from_event(event) == "chat"

    def test_native_default(self):
        event = {"event_type": "agent.x.tool_call_start", "tool_kwargs": {}}
        assert infer_tool_source_from_event(event) == "native"


class TestNormalizeToolParameters:
    def test_native_operational_event(self):
        event = {
            "event_type": "agent.onboarding_agent.tool_call_start",
            "agent_name": "onboarding_agent",
            "tool_name": "update_vendor_status",
            "tool_kwargs": {"vendor_id": 1, "status": "approved"},
        }
        payload = normalize_tool_parameters(event)
        assert payload["tool_name"] == "update_vendor_status"
        assert payload["tool_source"] == "native"
        assert payload["mapped_from_event_type"] == "tool_call_start"
        assert payload["arguments"]["vendor_id"] == 1

    def test_mcp_operational_event(self):
        event = {
            "event_type": "agent.invoice_agent.mcp_tool_call_start",
            "agent_name": "invoice_agent",
            "tool_name": "send_email",
            "namespaced_tool_name": "finmail__send_email",
            "mcp_server": "finmail",
            "tool_arguments": {"to": ["a@test.com"], "subject": "hi"},
        }
        payload = normalize_tool_parameters(event)
        assert payload["tool_name"] == "finmail__send_email"
        assert payload["tool_source"] == "mcp"
        assert payload["mcp_server"] == "finmail"
        assert payload["arguments"]["subject"] == "hi"


class TestNormalizeToolOutput:
    def test_success_native(self):
        event = {
            "event_type": "agent.foo.tool_call_success",
            "tool_name": "get_vendor",
            "tool_output": {"id": 1},
            "duration_ms": 42.5,
            "agent_name": "foo",
        }
        payload = normalize_tool_output(event)
        assert payload["success"] is True
        assert payload["output"] == {"id": 1}
        assert payload["duration_ms"] == 42.5

    def test_failure_mcp(self):
        event = {
            "event_type": "agent.foo.mcp_tool_call_failure",
            "namespaced_tool_name": "findrive__get_file",
            "mcp_server": "findrive",
            "error_type": "ValueError",
            "error_message": "not found",
            "duration_ms": 10,
        }
        payload = normalize_tool_output(event)
        assert payload["success"] is False
        assert payload["tool_name"] == "findrive__get_file"
        assert payload["tool_source"] == "mcp"
        assert payload["error_type"] == "ValueError"
        assert "output" not in payload
