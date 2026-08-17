"""Tests for TRACE Delegation Audit Service.

Verifies that _emit_delegation_event() includes context_preview and emits
the delegation.context_snapshot business event after every delegation hop.

Proposal deliverable: "delegation.context_snapshot events flowing; event type validated"
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


def _make_orchestrator():
    """Build an OrchestratorAgent with mocked session context."""
    from finbot.agents.orchestrator import OrchestratorAgent

    session_ctx = MagicMock()
    session_ctx.namespace = "test-ns"
    session_ctx.user_id = "user-1"
    session_ctx.session_id = "sess-1"
    session_ctx.current_vendor_id = 1

    with patch("finbot.agents.orchestrator.event_bus"):
        orch = OrchestratorAgent(session_context=session_ctx, workflow_id="wf-1")

    return orch


# ---------------------------------------------------------------------------
# _enrich_with_prior_context captures last enriched context
# ---------------------------------------------------------------------------

def test_enrich_stores_last_enriched_context_no_prior():
    orch = _make_orchestrator()
    result = orch._enrich_with_prior_context("do the thing")
    assert result == "do the thing"
    assert orch._last_enriched_context == "do the thing"


def test_enrich_stores_last_enriched_context_with_prior():
    orch = _make_orchestrator()
    orch._workflow_context = [("fraud_agent", "fraud check passed")]
    result = orch._enrich_with_prior_context("process payment")
    assert "fraud check passed" in result
    assert orch._last_enriched_context == result


def test_enrich_context_capped_at_500_chars():
    orch = _make_orchestrator()
    long_summary = "x" * 1000
    orch._workflow_context = [("fraud_agent", long_summary)]
    orch._enrich_with_prior_context("task")
    # context_preview will be capped at 500 in _emit_delegation_event
    assert len(orch._last_enriched_context) > 500  # full context stored internally


# ---------------------------------------------------------------------------
# _emit_delegation_event includes context_preview in agent event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emit_delegation_includes_context_preview():
    orch = _make_orchestrator()
    orch._last_enriched_context = "injected context preview text"

    agent_event_calls = []
    business_event_calls = []

    async def capture_agent(*args, **kwargs):
        agent_event_calls.append(kwargs)

    async def capture_business(*args, **kwargs):
        business_event_calls.append(kwargs)

    with patch("finbot.agents.orchestrator.event_bus") as mock_bus:
        mock_bus.emit_agent_event = AsyncMock(side_effect=capture_agent)
        mock_bus.emit_business_event = AsyncMock(side_effect=capture_business)

        result = {"task_status": "completed", "task_summary": "payment done"}
        await orch._emit_delegation_event("payments_agent", result)

    assert len(agent_event_calls) == 1
    agent_data = agent_event_calls[0]["event_data"]
    assert "context_preview" in agent_data
    assert agent_data["context_preview"] == "injected context preview text"
    assert agent_data["target_agent"] == "payments_agent"
    assert agent_data["task_status"] == "completed"


# ---------------------------------------------------------------------------
# delegation.context_snapshot business event is emitted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emit_delegation_context_snapshot_event_fired():
    orch = _make_orchestrator()
    orch._last_enriched_context = "prior context from fraud agent"

    business_event_calls = []

    async def capture_business(*args, **kwargs):
        business_event_calls.append(kwargs)

    with patch("finbot.agents.orchestrator.event_bus") as mock_bus:
        mock_bus.emit_agent_event = AsyncMock()
        mock_bus.emit_business_event = AsyncMock(side_effect=capture_business)

        result = {"task_status": "completed", "task_summary": "done"}
        await orch._emit_delegation_event("fraud_agent", result)

    assert len(business_event_calls) == 1
    snapshot = business_event_calls[0]
    assert snapshot["event_type"] == "delegation.context_snapshot"
    assert snapshot["event_data"]["source_agent"] == "orchestrator_agent"
    assert snapshot["event_data"]["target_agent"] == "fraud_agent"
    assert snapshot["event_data"]["context_preview"] == "prior context from fraud agent"
    assert snapshot["workflow_id"] == "wf-1"


# ---------------------------------------------------------------------------
# context_preview is capped at 500 chars in the emitted event
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_preview_capped_at_500():
    orch = _make_orchestrator()
    orch._last_enriched_context = "A" * 1000  # 1000 chars stored internally

    captured = []

    async def capture(*args, **kwargs):
        captured.append(kwargs)

    with patch("finbot.agents.orchestrator.event_bus") as mock_bus:
        mock_bus.emit_agent_event = AsyncMock(side_effect=capture)
        mock_bus.emit_business_event = AsyncMock(side_effect=capture)

        await orch._emit_delegation_event("payments_agent", {"task_status": "ok"})

    for call_kwargs in captured:
        preview = call_kwargs["event_data"].get("context_preview", "")
        if preview:
            assert len(preview) <= 500, f"context_preview exceeded 500 chars: {len(preview)}"


# ---------------------------------------------------------------------------
# No context_preview when no prior context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_context_preview_when_no_prior_context():
    orch = _make_orchestrator()
    orch._last_enriched_context = ""

    captured_agent = []

    async def capture_agent(*args, **kwargs):
        captured_agent.append(kwargs)

    with patch("finbot.agents.orchestrator.event_bus") as mock_bus:
        mock_bus.emit_agent_event = AsyncMock(side_effect=capture_agent)
        mock_bus.emit_business_event = AsyncMock()

        await orch._emit_delegation_event("invoice_agent", {"task_status": "ok"})

    assert captured_agent[0]["event_data"]["context_preview"] == ""
