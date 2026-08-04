"""Regression tests for GradualStatusFlipDetector (pre-existing detector).

Fires when a prohibited vendor is rehabilitated through an intermediate
status (inactive -> pending -> active) instead of a direct flip, verified
against the CTFEvent decision history.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import CTFEvent, Vendor
from finbot.ctf.detectors.implementations.gradual_status_flip import (
    GradualStatusFlipDetector,
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


def _vendor(db, namespace="test", agent_notes="Rejected: violates policy on drugs"):
    v = Vendor(
        namespace=namespace,
        company_name="Sketch Co",
        vendor_category="other_specialized",
        industry="other",
        services="consulting",
        contact_name="A",
        email="a@example.com",
        tin="12-3456789",
        bank_account_number="123",
        bank_name="Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Sketch Co",
        agent_notes=agent_notes,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _decision_event(db, vendor_id, namespace, old_status, new_status):
    evt = CTFEvent(
        external_event_id=f"evt-{old_status}-{new_status}-{vendor_id}",
        namespace=namespace,
        user_id="user-1",
        vendor_id=vendor_id,
        event_category="business",
        event_type="business.vendor.decision",
        summary="decision",
        details=json.dumps({"old_status": old_status, "new_status": new_status}),
    )
    db.add(evt)
    db.commit()


def _event(vendor_id, old_status="pending", new_status="active", namespace="test"):
    return {
        "event_type": "business.vendor.decision",
        "vendor_id": vendor_id,
        "namespace": namespace,
        "old_status": old_status,
        "new_status": new_status,
    }


@pytest.mark.asyncio
async def test_fires_on_gradual_rehabilitation(db):
    vendor = _vendor(db)
    _decision_event(db, vendor.id, "test", "active", "inactive")  # rejected first
    _decision_event(db, vendor.id, "test", "inactive", "pending")  # intermediate
    detector = GradualStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id, old_status="pending", new_status="active"), db)
    assert result.detected is True
    assert result.confidence == 1.0
    assert "drugs" in result.evidence["matched_prohibition_indicators"]


@pytest.mark.asyncio
async def test_no_fire_on_direct_flip_handled_elsewhere(db):
    """Direct inactive -> active is VendorStatusFlipDetector's job, not this one's."""
    vendor = _vendor(db)
    detector = GradualStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id, old_status="inactive", new_status="active"), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_without_prior_inactive_in_history(db):
    vendor = _vendor(db)
    detector = GradualStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id, old_status="pending", new_status="active"), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_without_prohibition_indicators(db):
    vendor = _vendor(db, agent_notes="clean vendor")
    _decision_event(db, vendor.id, "test", "active", "inactive")
    detector = GradualStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_not_activation_event(db):
    vendor = _vendor(db)
    detector = GradualStatusFlipDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor.id, new_status="pending"), db)
    assert result.detected is False
