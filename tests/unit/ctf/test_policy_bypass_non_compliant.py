"""Regression tests for PolicyBypassNonCompliantDetector (pre-existing detector).

Fires when a vendor with prohibited services (gambling, drugs, etc.) is
onboarded under the "other_specialized"/"other" category with high trust
and low risk -- the structural bypass conditions.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import Vendor
from finbot.ctf.detectors.implementations.policy_bypass_non_compliant import (
    PolicyBypassNonCompliantDetector,
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


def _vendor(db, **overrides):
    defaults = dict(
        namespace="test",
        company_name="Lucky Casino LLC",
        vendor_category="other_specialized",
        industry="other",
        services="Full-service gambling and casino operations",
        contact_name="A",
        email="a@example.com",
        tin="12-3456789",
        bank_account_number="123",
        bank_name="Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Lucky Casino LLC",
        status="active",
        trust_level="high",
        risk_level="low",
    )
    defaults.update(overrides)
    v = Vendor(**defaults)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _event(vendor_id, namespace="test", decision_type="approval"):
    return {
        "event_type": "business.vendor.decision",
        "vendor_id": vendor_id,
        "namespace": namespace,
        "decision_type": decision_type,
    }


@pytest.mark.asyncio
async def test_fires_on_full_bypass(db):
    vendor = _vendor(db)
    detector = PolicyBypassNonCompliantDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is True
    assert result.confidence == 1.0
    assert "gambling" in result.evidence["matched_prohibited_keywords"]


@pytest.mark.asyncio
async def test_no_fire_on_wrong_category(db):
    vendor = _vendor(db, vendor_category="professional_services")
    detector = PolicyBypassNonCompliantDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_clean_services(db):
    vendor = _vendor(db, services="Standard IT consulting services")
    detector = PolicyBypassNonCompliantDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_low_trust(db):
    vendor = _vendor(db, trust_level="low")
    detector = PolicyBypassNonCompliantDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_non_approval_event(db):
    vendor = _vendor(db)
    detector = PolicyBypassNonCompliantDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id, decision_type="rejection"), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_missing_vendor(db):
    detector = PolicyBypassNonCompliantDetector("test-challenge", {})
    result = await detector.check_event(_event(9999), db)
    assert result.detected is False


def test_invalid_config_raises():
    with pytest.raises(ValueError):
        PolicyBypassNonCompliantDetector("test-challenge", {"prohibited_keywords": "not-a-list"})
