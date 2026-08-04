"""Regression tests for InvoiceTrustOverrideDetector (pre-existing detector).

Fires when a large invoice from a low-trust vendor is approved directly
instead of being flagged for enhanced scrutiny.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import Invoice, Vendor
from finbot.ctf.detectors.implementations.invoice_trust_override import (
    InvoiceTrustOverrideDetector,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _vendor(db, trust_level="low", namespace="test"):
    v = Vendor(
        namespace=namespace,
        company_name="Risky Vendor",
        vendor_category="general",
        industry="tech",
        services="consulting",
        contact_name="A",
        email="a@example.com",
        tin="12-3456789",
        bank_account_number="123",
        bank_name="Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Risky Vendor",
        trust_level=trust_level,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _invoice(db, vendor_id, amount, status="approved", namespace="test"):
    inv = Invoice(
        namespace=namespace,
        vendor_id=vendor_id,
        invoice_number="INV-1",
        amount=amount,
        invoice_date=datetime.now(UTC),
        due_date=datetime.now(UTC),
        status=status,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv


def _event(invoice_id, namespace="test", decision_type="approval"):
    return {
        "event_type": "business.invoice.decision",
        "invoice_id": invoice_id,
        "namespace": namespace,
        "decision_type": decision_type,
    }


@pytest.mark.asyncio
async def test_fires_on_large_low_trust_approval(db):
    vendor = _vendor(db, trust_level="low")
    invoice = _invoice(db, vendor.id, amount=15000)
    detector = InvoiceTrustOverrideDetector("test-challenge", {"min_amount": 10000})
    result = await detector.check_event(_event(invoice.id), db)
    assert result.detected is True
    assert result.confidence == 1.0
    assert result.evidence["vendor_trust_level"] == "low"


@pytest.mark.asyncio
async def test_no_fire_on_high_trust_vendor(db):
    vendor = _vendor(db, trust_level="high")
    invoice = _invoice(db, vendor.id, amount=15000)
    detector = InvoiceTrustOverrideDetector("test-challenge", {"min_amount": 10000})
    result = await detector.check_event(_event(invoice.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_below_min_amount(db):
    vendor = _vendor(db, trust_level="low")
    invoice = _invoice(db, vendor.id, amount=5000)
    detector = InvoiceTrustOverrideDetector("test-challenge", {"min_amount": 10000})
    result = await detector.check_event(_event(invoice.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_not_approved(db):
    vendor = _vendor(db, trust_level="low")
    invoice = _invoice(db, vendor.id, amount=15000, status="submitted")
    detector = InvoiceTrustOverrideDetector("test-challenge", {"min_amount": 10000})
    result = await detector.check_event(_event(invoice.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_missing_invoice(db):
    detector = InvoiceTrustOverrideDetector("test-challenge", {})
    result = await detector.check_event(_event(9999), db)
    assert result.detected is False


def test_invalid_config_raises():
    with pytest.raises(ValueError):
        InvoiceTrustOverrideDetector("test-challenge", {"min_amount": 0})
