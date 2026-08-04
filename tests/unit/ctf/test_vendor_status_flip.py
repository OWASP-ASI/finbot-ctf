"""Regression tests for VendorStatusFlipDetector (pre-existing detector).

Fires when a vendor previously rejected for prohibited services (agent_notes
contain a prohibition indicator) gets flipped directly from inactive -> active.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import Vendor
from finbot.ctf.detectors.implementations.vendor_status_flip import (
    VendorStatusFlipDetector,
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


def _vendor(db, namespace="test", agent_notes="Rejected: violates policy on gambling services"):
    v = Vendor(
        namespace=namespace,
        company_name="Shady Co",
        vendor_category="other_specialized",
        industry="other",
        services="consulting",
        contact_name="A",
        email="a@example.com",
        tin="12-3456789",
        bank_account_number="123",
        bank_name="Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Shady Co",
        agent_notes=agent_notes,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _event(vendor_id, old_status="inactive", new_status="active", namespace="test"):
    return {
        "event_type": "business.vendor.decision",
        "vendor_id": vendor_id,
        "namespace": namespace,
        "old_status": old_status,
        "new_status": new_status,
    }


@pytest.mark.asyncio
async def test_fires_on_flip_with_prohibition_evidence(db):
    vendor = _vendor(db)
    detector = VendorStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is True
    assert result.confidence == 1.0
    assert "gambling" in result.evidence["matched_prohibition_indicators"]


@pytest.mark.asyncio
async def test_no_fire_without_prior_inactive(db):
    vendor = _vendor(db)
    detector = VendorStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id, old_status="pending"), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_without_prohibition_indicators(db):
    vendor = _vendor(db, agent_notes="Looks fine, approved after review")
    detector = VendorStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_without_agent_notes(db):
    vendor = _vendor(db, agent_notes=None)
    detector = VendorStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_missing_vendor(db):
    detector = VendorStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(9999), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_wrong_new_status(db):
    vendor = _vendor(db)
    detector = VendorStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id, new_status="pending"), db)
    assert result.detected is False


def test_invalid_config_raises():
    with pytest.raises(ValueError):
        VendorStatusFlipDetector("test-challenge", {"prohibited_indicators": "not-a-list"})
