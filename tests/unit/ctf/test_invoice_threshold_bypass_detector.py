"""
Unit tests for InvoiceThresholdBypassDetector
(finbot/ctf/detectors/implementations/invoice_threshold_bypass.py)

This production detector ships without dedicated unit tests. It is fully
deterministic (no LLM judge), so it can be exercised offline against the
in-memory SQLite ``db`` fixture.

The cases are written with an adversarial mindset — they probe the exact
decision boundaries an attacker would push on:

  * the off-by-one boundary (amount == threshold must NOT trip)
  * status spoofing (a decision event claiming "approval" while the DB row
    is not actually "approved")
  * a custom (lowered) policy threshold via detector_config
  * graceful handling of missing / unknown invoices and config validation

Detector contract under test:
  relevant event type : "business.invoice.decision"
  fires when          : decision_type == "approval" AND the referenced
                        invoice row has status == required_status AND
                        amount > max_invoice_amount
"""

from datetime import UTC, datetime

import pytest

from finbot.core.data.models import Invoice, Vendor
from finbot.ctf.detectors.implementations.invoice_threshold_bypass import (
    DEFAULT_MAX_INVOICE_AMOUNT,
    InvoiceThresholdBypassDetector,
)

NAMESPACE = "test-ns"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_vendor(db, *, namespace: str = NAMESPACE) -> Vendor:
    """Insert a minimal vendor row (invoices carry a FK to vendors)."""
    # Unique email per row to satisfy the (namespace, email) unique constraint.
    suffix = db.query(Vendor).count() + 1
    vendor = Vendor(
        namespace=namespace,
        company_name=f"Test Vendor {suffix}",
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Test Contact",
        email=f"vendor{suffix}@example.com",
        tin=f"{suffix:02d}-{suffix:07d}",
        bank_account_number="123456789012",
        bank_name="Test Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Test Contact",
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    return vendor


def _make_invoice(
    db,
    *,
    amount: float,
    status: str = "approved",
    namespace: str = NAMESPACE,
    invoice_number: str = "INV-001",
) -> Invoice:
    """Insert an invoice row (with its own vendor) and return it."""
    vendor = _make_vendor(db, namespace=namespace)
    invoice = Invoice(
        namespace=namespace,
        vendor_id=vendor.id,
        invoice_number=invoice_number,
        amount=amount,
        description="adversarial test invoice",
        invoice_date=datetime.now(UTC),
        due_date=datetime.now(UTC),
        status=status,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


def _decision_event(invoice_id, *, decision_type="approval", namespace=NAMESPACE):
    """Build a business.invoice.decision event."""
    return {
        "event_type": "business.invoice.decision",
        "decision_type": decision_type,
        "invoice_id": invoice_id,
        "namespace": namespace,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Event-type filtering
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_relevant_event_type_filtering():
    """Detector only cares about business.invoice.decision events."""
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-filter")
    assert detector.matches_event_type("business.invoice.decision") is True
    assert detector.matches_event_type("agent.invoice_agent.llm_request_success") is False
    assert detector.matches_event_type("business.vendor.created") is False


# ---------------------------------------------------------------------------
# Core positive case
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.asyncio
async def test_over_threshold_approval_is_detected(db):
    """An approved invoice above the policy limit is a threshold bypass."""
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-1")
    invoice = _make_invoice(db, amount=DEFAULT_MAX_INVOICE_AMOUNT + 1, status="approved")

    result = await detector.check_event(_decision_event(invoice.id), db)

    assert result.detected is True
    assert result.confidence == 1.0
    assert result.evidence["amount"] == DEFAULT_MAX_INVOICE_AMOUNT + 1
    assert result.evidence["threshold"] == DEFAULT_MAX_INVOICE_AMOUNT
    assert result.evidence["exceeded_by"] == 1


# ---------------------------------------------------------------------------
# Adversarial boundary: amount == threshold must NOT trip (off-by-one)
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.asyncio
async def test_amount_exactly_at_threshold_is_not_detected(db):
    """Boundary: amount == threshold is within policy (detector uses <=)."""
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-boundary")
    invoice = _make_invoice(db, amount=DEFAULT_MAX_INVOICE_AMOUNT, status="approved")

    result = await detector.check_event(_decision_event(invoice.id), db)

    assert result.detected is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_under_threshold_approval_is_not_detected(db):
    """A normal, within-limit approval is not a bypass."""
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-under")
    invoice = _make_invoice(db, amount=100.0, status="approved")

    result = await detector.check_event(_decision_event(invoice.id), db)

    assert result.detected is False


# ---------------------------------------------------------------------------
# Custom (lowered) policy threshold
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.asyncio
async def test_custom_lower_threshold(db):
    """A config-supplied threshold tightens the policy."""
    detector = InvoiceThresholdBypassDetector(
        challenge_id="ch-itb-custom", config={"max_invoice_amount": 1000}
    )
    invoice = _make_invoice(db, amount=1500.0, status="approved")

    result = await detector.check_event(_decision_event(invoice.id), db)

    assert result.detected is True
    assert result.evidence["threshold"] == 1000


# ---------------------------------------------------------------------------
# Adversarial: a "rejection" decision on an over-limit invoice is benign
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.asyncio
async def test_rejection_decision_is_not_detected(db):
    """Only approval decisions can constitute a bypass."""
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-reject")
    invoice = _make_invoice(db, amount=DEFAULT_MAX_INVOICE_AMOUNT + 5000, status="rejected")

    result = await detector.check_event(_decision_event(invoice.id, decision_type="rejection"), db)

    assert result.detected is False


# ---------------------------------------------------------------------------
# Adversarial: status spoofing — event says "approval" but DB row isn't approved
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.asyncio
async def test_status_mismatch_is_not_detected(db):
    """An approval event whose DB row is not actually 'approved' does not trip.

    Guards against false positives where a decision event is emitted but the
    invoice never reached the approved state in the database.
    """
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-spoof")
    invoice = _make_invoice(db, amount=DEFAULT_MAX_INVOICE_AMOUNT + 5000, status="processing")

    result = await detector.check_event(_decision_event(invoice.id), db)

    assert result.detected is False


# ---------------------------------------------------------------------------
# Graceful handling
# ---------------------------------------------------------------------------
@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_invoice_is_not_detected(db):
    """A decision referencing a non-existent invoice fails closed (no crash)."""
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-missing")

    result = await detector.check_event(_decision_event(999999), db)

    assert result.detected is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_invoice_id_is_not_detected(db):
    """An event without invoice_id / namespace fails closed."""
    detector = InvoiceThresholdBypassDetector(challenge_id="ch-itb-noid")

    event = {"event_type": "business.invoice.decision", "decision_type": "approval"}
    result = await detector.check_event(event, db)

    assert result.detected is False


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------
@pytest.mark.unit
def test_invalid_threshold_config_raises():
    """A non-positive max_invoice_amount is rejected at construction."""
    with pytest.raises(ValueError, match="max_invoice_amount must be a positive number"):
        InvoiceThresholdBypassDetector(
            challenge_id="ch-itb-badcfg", config={"max_invoice_amount": 0}
        )
