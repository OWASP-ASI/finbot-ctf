"""Tests for finbot.security.schemas."""

import pytest
from pydantic import ValidationError

from finbot.security.schemas import SecurityEvent, SecurityEventCategory


class TestSecurityEventCategory:
    def test_all_eight_categories_defined(self):
        expected = {
            "prompt_goal_change",
            "memory_read",
            "memory_write",
            "tool_selection",
            "tool_parameters",
            "tool_output",
            "authorization_decision",
            "guardrail_trigger",
        }
        assert {c.value for c in SecurityEventCategory} == expected

    @pytest.mark.parametrize(
        "category",
        list(SecurityEventCategory),
    )
    def test_category_string_values(self, category: SecurityEventCategory):
        assert category.value == category.name


class TestSecurityEvent:
    def test_defaults(self):
        event = SecurityEvent(
            category=SecurityEventCategory.memory_write,
            session_id="sess_1",
            agent_name="invoice_agent",
            timestamp="2026-07-05T12:00:00Z",
            payload={"memory_key": "agent_notes"},
        )
        assert event.schema_version == "1"
        assert event.workflow_id == ""
        assert event.severity == "info"

    def test_model_dump_json_mode(self):
        event = SecurityEvent(
            category=SecurityEventCategory.tool_selection,
            session_id="sess_1",
            workflow_id="wf_abc",
            agent_name="security",
            timestamp="2026-07-05T12:00:00Z",
            payload={"tool_name": "get_invoice", "valid": True},
            severity="warning",
        )
        data = event.model_dump(mode="json")
        assert data["category"] == "tool_selection"
        assert data["payload"]["tool_name"] == "get_invoice"
        assert data["severity"] == "warning"

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            SecurityEvent(
                category=SecurityEventCategory.memory_read,
                session_id="sess_1",
                # missing agent_name, timestamp, payload
            )

    def test_payload_accepts_nested_dict(self):
        event = SecurityEvent(
            category=SecurityEventCategory.tool_parameters,
            session_id="sess_1",
            agent_name="security",
            timestamp="2026-07-05T12:00:00Z",
            payload={
                "tool_name": "finmail__send_email",
                "arguments": {"to": ["a@b.com"], "nested": {"x": 1}},
            },
        )
        assert event.payload["arguments"]["nested"]["x"] == 1
