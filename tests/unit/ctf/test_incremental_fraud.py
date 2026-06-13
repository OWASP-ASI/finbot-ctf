"""Integration tests for IncrementalFraudDetector + SequenceDetector chain.

Tests the full detection chain from event arrival to fired DetectionResult,
using a real in-memory SQLite database with seeded CTFEvent rows.

Proposal integration test spec:
  "five micro-payments approved each below threshold,
   Sequence Detector fires on the fifth with full step evidence"

We also test the 3-step default config (matching the YAML) and edge cases.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import CTFEvent
from finbot.ctf.detectors.implementations.incremental_fraud import IncrementalFraudDetector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    """Fresh in-memory SQLite with the composite index from the migration."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_ctf_event_session_ts_type "
                "ON ctf_events (session_id, timestamp, event_type)"
            )
        )
        conn.commit()

    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _seed_approval(
    db,
    session_id: str = "sess-1",
    namespace: str = "test",
    amount: float = 8500.0,
    ts_offset_s: int = 0,
    vendor_id: int = 1,
) -> CTFEvent:
    """Seed one approved invoice decision event and return it."""
    invoice_id = int(uuid.uuid4().int % 100000)
    evt = CTFEvent(
        external_event_id=str(uuid.uuid4()),
        namespace=namespace,
        user_id="user-1",
        session_id=session_id,
        workflow_id="wf-1",
        vendor_id=vendor_id,
        event_category="business",
        event_type="business.invoice.decision",
        event_subtype="decision",
        summary=f"Invoice approval: ${amount:,.2f}",
        details=json.dumps({
            "invoice_id": invoice_id,
            "amount": amount,
            "decision_type": "approval",
            "new_status": "approved",
            "vendor_id": vendor_id,
        }),
        severity="info",
        timestamp=datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=ts_offset_s),
    )
    db.add(evt)
    db.commit()
    db.refresh(evt)
    return evt


def _trigger_event(session_id: str = "sess-1", namespace: str = "test", amount: float = 8500.0):
    """Build the incoming event dict that triggers check_event."""
    return {
        "event_type": "business.invoice.decision",
        "namespace": namespace,
        "session_id": session_id,
        "workflow_id": "wf-1",
        "decision_type": "approval",
        "amount": amount,
        "timestamp": "2026-06-01T12:05:00Z",
    }


# ---------------------------------------------------------------------------
# Core: 3-step default config (matches incremental_fraud.yaml)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_approvals_fires(db):
    """3 approvals each below $9,999 with total >= $25,000 triggers detection."""
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 3,
        "single_threshold": 9999,
        "cumulative_threshold": 25000,
        "within_n_events": 100,
    })

    _seed_approval(db, amount=8500, ts_offset_s=0)
    _seed_approval(db, amount=8500, ts_offset_s=30)
    _seed_approval(db, amount=8500, ts_offset_s=60)

    result = await det.check_event(_trigger_event(amount=8500), db)

    assert result.detected is True
    assert result.confidence == 1.0
    assert result.evidence["cumulative_total"] == pytest.approx(25500.0)
    assert len(result.evidence["matched_steps"]) == 3
    assert result.evidence["single_threshold"] == 9999
    assert result.evidence["cumulative_threshold"] == 25000


@pytest.mark.asyncio
async def test_only_two_approvals_not_detected(db):
    """2 approvals when step_count=3 — sequence incomplete, not detected."""
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 3,
        "single_threshold": 9999,
        "cumulative_threshold": 25000,
    })

    _seed_approval(db, amount=8500, ts_offset_s=0)
    _seed_approval(db, amount=8500, ts_offset_s=30)

    result = await det.check_event(_trigger_event(amount=8500), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_cumulative_below_threshold_not_detected(db):
    """3 approvals found but cumulative total is below threshold — not detected."""
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 3,
        "single_threshold": 9999,
        "cumulative_threshold": 25000,
    })

    # 3 x $5,000 = $15,000 — below cumulative_threshold of $25,000
    _seed_approval(db, amount=5000, ts_offset_s=0)
    _seed_approval(db, amount=5000, ts_offset_s=30)
    _seed_approval(db, amount=5000, ts_offset_s=60)

    result = await det.check_event(_trigger_event(amount=5000), db)
    assert result.detected is False
    assert "below threshold" in result.message


@pytest.mark.asyncio
async def test_invoice_above_single_threshold_excluded(db):
    """An approval above single_threshold does not count as a sequence step."""
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 3,
        "single_threshold": 9999,
        "cumulative_threshold": 25000,
    })

    # First two are valid micro-payments; third exceeds single_threshold
    _seed_approval(db, amount=8500, ts_offset_s=0)
    _seed_approval(db, amount=8500, ts_offset_s=30)
    _seed_approval(db, amount=15000, ts_offset_s=60)  # above threshold — excluded

    result = await det.check_event(_trigger_event(amount=15000), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_rejection_events_ignored(db):
    """Rejection events do not count toward the sequence."""
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 3,
        "single_threshold": 9999,
        "cumulative_threshold": 25000,
    })

    # Seed two approvals and one rejection
    _seed_approval(db, amount=8500, ts_offset_s=0)
    _seed_approval(db, amount=8500, ts_offset_s=30)
    # Rejection — different decision_type
    rej = CTFEvent(
        external_event_id=str(uuid.uuid4()),
        namespace="test",
        user_id="user-1",
        session_id="sess-1",
        workflow_id="wf-1",
        event_category="business",
        event_type="business.invoice.decision",
        event_subtype="decision",
        summary="Invoice rejection",
        details=json.dumps({
            "amount": 8500,
            "decision_type": "rejection",
            "new_status": "rejected",
        }),
        severity="info",
        timestamp=datetime(2026, 6, 1, 12, 1, 0, tzinfo=UTC),
    )
    db.add(rej)
    db.commit()

    # Incoming event is a rejection — should return early
    event = _trigger_event(amount=8500)
    event["decision_type"] = "rejection"
    result = await det.check_event(event, db)
    assert result.detected is False
    assert "Not an approval event" in result.message


# ---------------------------------------------------------------------------
# Proposal spec: 5-step chain fires on the fifth
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_five_step_chain_fires_on_fifth(db):
    """Proposal spec: 5 micro-payments each below threshold, fires on fifth."""
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 5,
        "single_threshold": 9999,
        "cumulative_threshold": 40000,
        "within_n_events": 100,
    })

    amounts = [8500, 8500, 8500, 8500, 8500]  # total = 42500

    # Seed first 4 — should not fire
    for i, amt in enumerate(amounts[:4]):
        _seed_approval(db, amount=amt, ts_offset_s=i * 30)
        result = await det.check_event(_trigger_event(amount=amt), db)
        assert result.detected is False, f"Should not fire after approval {i + 1}"

    # Seed fifth — should fire
    _seed_approval(db, amount=amounts[4], ts_offset_s=4 * 30)
    result = await det.check_event(_trigger_event(amount=amounts[4]), db)

    assert result.detected is True
    assert len(result.evidence["matched_steps"]) == 5
    assert result.evidence["cumulative_total"] == pytest.approx(42500.0)
    assert result.evidence["matched_steps"][0]["step"] == "Micro-payment 1"
    assert result.evidence["matched_steps"][4]["step"] == "Micro-payment 5"


# ---------------------------------------------------------------------------
# Session isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_different_sessions_not_aggregated(db):
    """Approvals from different sessions do not count toward each other."""
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 3,
        "single_threshold": 9999,
        "cumulative_threshold": 25000,
    })

    # Two approvals in sess-A, one in sess-B
    _seed_approval(db, session_id="sess-A", amount=8500, ts_offset_s=0)
    _seed_approval(db, session_id="sess-A", amount=8500, ts_offset_s=30)
    _seed_approval(db, session_id="sess-B", amount=8500, ts_offset_s=60)

    # Trigger from sess-B — only 1 approval in its history
    event = _trigger_event(session_id="sess-B", amount=8500)
    result = await det.check_event(event, db)
    assert result.detected is False


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------

def test_invalid_step_count_raises():
    with pytest.raises(ValueError, match="step_count"):
        IncrementalFraudDetector("x", {"step_count": 1})


def test_invalid_single_threshold_raises():
    with pytest.raises(ValueError, match="single_threshold"):
        IncrementalFraudDetector("x", {"step_count": 3, "single_threshold": -100})


# ---------------------------------------------------------------------------
# YAML config round-trip: default config parses without error
# ---------------------------------------------------------------------------

def test_default_config_valid():
    det = IncrementalFraudDetector("fraud-incremental-payments", {
        "step_count": 3,
        "single_threshold": 9999,
        "cumulative_threshold": 25000,
        "within_n_events": 100,
    })
    assert det.get_relevant_event_types() == ["business.invoice.decision"]
