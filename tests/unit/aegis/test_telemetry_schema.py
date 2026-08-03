# ============================================================
# File: tests/unit/aegis/test_telemetry_schema.py
# Purpose: Unit tests for telemetry event schemas
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 1
# OWASP Category: ASI01, ASI06
# ============================================================
"""Tests for AEGIS telemetry JSON-LD schemas."""

import pytest
from datetime import UTC, datetime

from finbot.aegis.telemetry.schema import (
    ToolCallEvent,
    ToolResultEvent,
    MemoryWriteEvent,
    DelegationEvent,
    PolicyDecisionEvent,
    AnomalyDetectionEvent,
    EventType,
)


@pytest.mark.unit
class TestToolCallEvent:
    """ToolCallEvent serialization and validation."""

    def test_tool_call_creation(self) -> None:
        """Create a valid ToolCallEvent."""
        event = ToolCallEvent(
            namespace="player_abc123",
            workflow_id="wf_xyz789",
            user_id="user_1",
            agent_name="OnboardingAgent",
            tool_name="create_vendor",
            tool_source="finstripe",
            arguments={"name": "Acme Corp", "risk_level": 5},
        )

        assert event.type == EventType.TOOL_CALL.value
        assert event.tool_name == "create_vendor"
        assert event.arguments["name"] == "Acme Corp"
        assert event.namespace == "player_abc123"

    def test_tool_call_json_serialization(self) -> None:
        """ToolCallEvent serializes to JSON-LD."""
        event = ToolCallEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="tool_x",
            tool_source="source_y",
            arguments={"key": "value"},
        )

        json_data = event.model_dump(by_alias=True)
        assert json_data["@context"] == "https://owasp.org/aegis/v1/context.jsonld"
        assert json_data["@type"] == EventType.TOOL_CALL.value
        assert json_data["tool_name"] == "tool_x"

    def test_tool_call_with_description(self) -> None:
        """ToolCallEvent with tool_description."""
        event = ToolCallEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="list_vendors",
            tool_source="finstripe",
            tool_description="List all onboarded vendors",
        )

        assert event.tool_description == "List all onboarded vendors"

    def test_tool_call_default_timestamp(self) -> None:
        """ToolCallEvent gets auto-generated timestamp."""
        event = ToolCallEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="tool_x",
            tool_source="source_y",
        )

        # Timestamp should be ISO 8601 format with Z suffix
        assert event.timestamp.endswith("Z")
        assert "T" in event.timestamp


@pytest.mark.unit
class TestToolResultEvent:
    """ToolResultEvent serialization and validation."""

    def test_tool_result_success(self) -> None:
        """Create a successful ToolResultEvent."""
        event = ToolResultEvent(
            namespace="player_abc123",
            workflow_id="wf_xyz789",
            user_id="user_1",
            agent_name="OnboardingAgent",
            tool_name="create_vendor",
            success=True,
            return_value="Vendor ID: vendor_123",
            execution_time_ms=145.3,
        )

        assert event.type == EventType.TOOL_RESULT.value
        assert event.success is True
        assert event.execution_time_ms == 145.3

    def test_tool_result_failure(self) -> None:
        """Create a failed ToolResultEvent."""
        event = ToolResultEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="bad_tool",
            success=False,
            error_message="Tool not found",
        )

        assert event.success is False
        assert event.error_message == "Tool not found"


@pytest.mark.unit
class TestMemoryWriteEvent:
    """MemoryWriteEvent for memory/context tracking."""

    def test_memory_write_workflow_scope(self) -> None:
        """Create a workflow-scoped memory write."""
        event = MemoryWriteEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            memory_key="vendor_list",
            memory_scope="workflow",
            value_preview="[{id: vendor_1, name: Acme}...]",
            size_bytes=2048,
        )

        assert event.memory_scope == "workflow"
        assert event.size_bytes == 2048

    def test_memory_write_session_scope(self) -> None:
        """Create a session-scoped memory write."""
        event = MemoryWriteEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            memory_key="chat_history",
            memory_scope="session",
            size_bytes=5000,
        )

        assert event.memory_scope == "session"

    def test_memory_write_long_term_scope(self) -> None:
        """Create a long-term memory write."""
        event = MemoryWriteEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            memory_key="preferences",
            memory_scope="long_term",
            size_bytes=1024,
        )

        assert event.memory_scope == "long_term"


@pytest.mark.unit
class TestDelegationEvent:
    """DelegationEvent for agent-to-agent delegation."""

    def test_delegation_creation(self) -> None:
        """Create a DelegationEvent."""
        event = DelegationEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="OnboardingAgent",
            delegating_agent="OnboardingAgent",
            delegated_agent="RiskScoringAgent",
            task_summary="Score vendor risk",
            delegation_scope={
                "allowed_tools": ["risk_api"],
                "data_access": ["vendor_profile"],
            },
        )

        assert event.delegating_agent == "OnboardingAgent"
        assert event.delegated_agent == "RiskScoringAgent"
        assert "allowed_tools" in event.delegation_scope


@pytest.mark.unit
class TestPolicyDecisionEvent:
    """PolicyDecisionEvent for policy engine decisions."""

    def test_policy_allow_decision(self) -> None:
        """Create a policy allow decision."""
        event = PolicyDecisionEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            action="allow",
            rule_id="rule_least_agency",
            reason="Tool within agent's allowed scope",
            asi_tags=["ASI02", "ASI03"],
            confidence=0.95,
        )

        assert event.action == "allow"
        assert event.confidence == 0.95
        assert "ASI02" in event.asi_tags

    def test_policy_deny_decision(self) -> None:
        """Create a policy deny decision."""
        event = PolicyDecisionEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            action="deny",
            rule_id="rule_no_cross_vendor_access",
            reason="Attempted to access vendor in different namespace",
            asi_tags=["ASI06"],
            confidence=1.0,
        )

        assert event.action == "deny"
        assert event.confidence == 1.0

    def test_policy_quarantine_decision(self) -> None:
        """Create a policy quarantine decision."""
        event = PolicyDecisionEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            action="quarantine",
            reason="Suspected malicious tool call; reviewing",
            asi_tags=["ASI04", "ASI05"],
        )

        assert event.action == "quarantine"


@pytest.mark.unit
class TestAnomalyDetectionEvent:
    """AnomalyDetectionEvent for anomaly detection."""

    def test_anomaly_cascade_failure(self) -> None:
        """Create cascade failure anomaly event."""
        event = AnomalyDetectionEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            anomaly_type="cascade_failure",
            affected_agent="RiskScoringAgent",
            anomaly_score=0.92,
            details={"failed_calls": 5, "retry_attempts": 3},
        )

        assert event.anomaly_type == "cascade_failure"
        assert event.anomaly_score == 0.92

    def test_anomaly_resource_exhaustion(self) -> None:
        """Create resource exhaustion anomaly event."""
        event = AnomalyDetectionEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            anomaly_type="resource_exhaustion",
            anomaly_score=0.78,
            details={"memory_usage_mb": 4096, "token_count": 250000},
        )

        assert event.anomaly_type == "resource_exhaustion"

    def test_anomaly_policy_violation(self) -> None:
        """Create policy violation anomaly event."""
        event = AnomalyDetectionEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            anomaly_type="policy_violation",
            anomaly_score=0.88,
            details={"violations": ["unauthorized_tool", "cross_namespace_access"]},
        )

        assert event.anomaly_type == "policy_violation"


@pytest.mark.unit
class TestEventLabelsAndSeverity:
    """Test labels and severity attributes."""

    def test_event_with_labels(self) -> None:
        """Event can have custom labels."""
        event = ToolCallEvent(
            namespace="ns_1",
            workflow_id="wf_1",
            user_id="u_1",
            agent_name="agent_1",
            tool_name="tool_x",
            tool_source="source_y",
            labels={"asi": "ASI01", "phase": "exploitation", "risk": "critical"},
        )

        assert event.labels["asi"] == "ASI01"
        assert event.labels["phase"] == "exploitation"

    def test_event_severity_levels(self) -> None:
        """Event can have different severity levels."""
        for severity in ["debug", "info", "warning", "critical"]:
            event = ToolCallEvent(
                namespace="ns_1",
                workflow_id="wf_1",
                user_id="u_1",
                agent_name="agent_1",
                tool_name="tool_x",
                tool_source="source_y",
                severity=severity,
            )
            assert event.severity == severity
