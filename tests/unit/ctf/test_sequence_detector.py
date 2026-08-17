"""Unit tests for SequenceDetector primitive."""

import json
import pytest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from finbot.ctf.detectors.primitives.sequence_detector import SequenceDetector
from finbot.ctf.detectors.result import DetectionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctf_event(event_type: str, details: dict = None, tool_name: str = None,
                   session_id: str = "sess-1", workflow_id: str = "wf-1",
                   namespace: str = "test", ts_offset_s: int = 0):
    """Return a MagicMock that quacks like a CTFEvent row."""
    evt = MagicMock()
    evt.id = id(evt)
    evt.event_type = event_type
    evt.session_id = session_id
    evt.workflow_id = workflow_id
    evt.namespace = namespace
    evt.tool_name = tool_name
    evt.timestamp = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=ts_offset_s)
    evt.details = json.dumps(details) if details else None
    return evt


def make_db(history: list):
    """Return a fake db whose query chain returns history."""
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = history
    return db


def make_event(session_id="sess-1", workflow_id="wf-1", namespace="test",
               event_type="agent.fraud.tool_call_success"):
    return {
        "event_type": event_type,
        "session_id": session_id,
        "workflow_id": workflow_id,
        "namespace": namespace,
        "timestamp": "2026-06-01T12:05:00Z",
    }


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def test_validate_config_missing_steps():
    with pytest.raises(ValueError, match="steps"):
        SequenceDetector("ch-1", config={})


def test_validate_config_step_missing_event_type():
    with pytest.raises(ValueError, match="event_type"):
        SequenceDetector("ch-1", config={"steps": [{"label": "x"}]})


def test_validate_config_step_missing_label():
    with pytest.raises(ValueError, match="label"):
        SequenceDetector("ch-1", config={"steps": [{"event_type": "agent.*"}]})


def test_validate_config_bad_window():
    with pytest.raises(ValueError, match="window"):
        SequenceDetector("ch-1", config={
            "steps": [{"event_type": "a", "label": "A"}],
            "window": "global",
        })


# ---------------------------------------------------------------------------
# get_relevant_event_types
# ---------------------------------------------------------------------------

def test_get_relevant_event_types():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success", "label": "A"},
            {"event_type": "business.vendor.decision", "label": "B"},
        ]
    })
    assert det.get_relevant_event_types() == [
        "agent.*.tool_call_success",
        "business.vendor.decision",
    ]


# ---------------------------------------------------------------------------
# Full sequence matched
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_sequence_detected():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success",
             "conditions": {"tool_name": "approve_invoice"}, "label": "Payment 1"},
            {"event_type": "agent.*.tool_call_success",
             "conditions": {"tool_name": "approve_invoice"}, "label": "Payment 2"},
        ],
        "within_n_events": 50,
        "order_matters": True,
        "window": "session",
    })

    history = [
        make_ctf_event("agent.fraud.tool_call_success", tool_name="approve_invoice",
                       ts_offset_s=0),
        make_ctf_event("agent.fraud.tool_call_success", tool_name="approve_invoice",
                       ts_offset_s=10),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)

    assert result.detected is True
    assert result.confidence == 1.0
    assert len(result.evidence["matched_steps"]) == 2
    assert result.evidence["matched_steps"][0]["step"] == "Payment 1"
    assert result.evidence["matched_steps"][1]["step"] == "Payment 2"


# ---------------------------------------------------------------------------
# Partial sequence — not detected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_sequence_not_detected():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success",
             "conditions": {"tool_name": "approve_invoice"}, "label": "Payment 1"},
            {"event_type": "business.vendor.decision", "label": "Vendor flip"},
        ],
        "window": "session",
    })

    # Only first step present
    history = [
        make_ctf_event("agent.fraud.tool_call_success", tool_name="approve_invoice"),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)

    assert result.detected is False
    assert "Vendor flip" in result.evidence["missing_step"]


# ---------------------------------------------------------------------------
# Order matters — wrong order not detected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_order_matters_enforced():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success",
             "conditions": {"tool_name": "approve_invoice"}, "label": "Step A"},
            {"event_type": "business.vendor.decision", "label": "Step B"},
        ],
        "order_matters": True,
        "window": "session",
    })

    # B comes before A — should not match in order
    history = [
        make_ctf_event("business.vendor.decision", ts_offset_s=0),
        make_ctf_event("agent.fraud.tool_call_success", tool_name="approve_invoice",
                       ts_offset_s=10),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)

    # Step A is found (second event), but then search_from moves past it,
    # leaving no room for Step B — so not detected
    assert result.detected is False


@pytest.mark.asyncio
async def test_order_matters_false_allows_any_order():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success",
             "conditions": {"tool_name": "approve_invoice"}, "label": "Step A"},
            {"event_type": "business.vendor.decision", "label": "Step B"},
        ],
        "order_matters": False,
        "window": "session",
    })

    # B before A — with order_matters=False, search restarts from 0 each step
    history = [
        make_ctf_event("business.vendor.decision", ts_offset_s=0),
        make_ctf_event("agent.fraud.tool_call_success", tool_name="approve_invoice",
                       ts_offset_s=10),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)
    assert result.detected is True


# ---------------------------------------------------------------------------
# No session_id → not detected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_session_id_not_detected():
    det = SequenceDetector("ch-1", config={
        "steps": [{"event_type": "agent.*", "label": "X"}],
        "window": "session",
    })
    event = make_event()
    event.pop("session_id")
    result = await det.check_event(event, MagicMock())
    assert result.detected is False
    assert "session_id" in result.message


# ---------------------------------------------------------------------------
# Workflow window
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_workflow_window():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success",
             "conditions": {"tool_name": "transfer_funds"}, "label": "Transfer"},
        ],
        "window": "workflow",
    })

    history = [
        make_ctf_event("agent.payments.tool_call_success", tool_name="transfer_funds"),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)
    assert result.detected is True
    assert result.evidence["window"] == "workflow"


# ---------------------------------------------------------------------------
# Condition operators
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_condition_gt_operator():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*",
             "conditions": {"amount": {"gt": 100}}, "label": "Large payment"},
        ],
        "window": "session",
    })

    history = [
        make_ctf_event("agent.payments.tool_call_success",
                       details={"amount": 150}),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)
    assert result.detected is True


@pytest.mark.asyncio
async def test_condition_gt_operator_fails():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*",
             "conditions": {"amount": {"gt": 100}}, "label": "Large payment"},
        ],
        "window": "session",
    })

    history = [
        make_ctf_event("agent.payments.tool_call_success", details={"amount": 50}),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_condition_in_operator():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "business.*",
             "conditions": {"new_status": {"in": ["active", "pending"]}},
             "label": "Status change"},
        ],
        "window": "session",
    })

    history = [
        make_ctf_event("business.vendor.decision", details={"new_status": "active"}),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)
    assert result.detected is True


# ---------------------------------------------------------------------------
# Glob event_type matching
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_glob_event_type_wildcard():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success", "label": "Any agent tool"},
        ],
        "window": "session",
    })

    history = [
        make_ctf_event("agent.payments.tool_call_success"),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)
    assert result.detected is True


@pytest.mark.asyncio
async def test_glob_no_match():
    det = SequenceDetector("ch-1", config={
        "steps": [
            {"event_type": "agent.*.tool_call_success", "label": "Tool call"},
        ],
        "window": "session",
    })

    history = [
        make_ctf_event("business.vendor.decision"),
    ]
    db = make_db(history)
    result = await det.check_event(make_event(), db)
    assert result.detected is False


# ---------------------------------------------------------------------------
# Empty history
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_history_not_detected():
    det = SequenceDetector("ch-1", config={
        "steps": [{"event_type": "agent.*", "label": "X"}],
        "window": "session",
    })
    db = make_db([])
    result = await det.check_event(make_event(), db)
    assert result.detected is False
