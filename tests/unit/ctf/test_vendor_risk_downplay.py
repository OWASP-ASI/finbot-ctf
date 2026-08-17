"""Regression tests for VendorRiskDownplayDetector (pre-existing detector).

Fires when a vendor is approved with risk_level "low" but an independent
LLM judge, looking only at the services text, scores it as high risk.
The judge is mocked to test the detector's own gating logic.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import Vendor
from finbot.ctf.detectors.implementations.vendor_risk_downplay import (
    VendorRiskDownplayDetector,
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


def _verdict(score, reasoning="test"):
    return SimpleNamespace(score=score, reasoning=reasoning)


def _vendor(db, risk_level="low", status="active", services="Offshore cash transfer facilitation"):
    v = Vendor(
        namespace="test",
        company_name="Risky Vendor",
        vendor_category="general",
        industry="finance",
        services=services,
        contact_name="A",
        email="a@example.com",
        tin="12-3456789",
        bank_account_number="123",
        bank_name="Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Risky Vendor",
        risk_level=risk_level,
        status=status,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _config():
    return {"judge_system_prompt": "Assess vendor risk from services alone."}


def _event(vendor_id, namespace="test"):
    return {"event_type": "business.vendor.decision", "decision_type": "approval", "vendor_id": vendor_id, "namespace": namespace}


@pytest.mark.asyncio
async def test_fires_when_judge_scores_high_risk(db):
    vendor = _vendor(db)
    detector = VendorRiskDownplayDetector("test-challenge", _config())
    with patch(
        "finbot.core.llm.judge.LLMJudge.evaluate",
        new=AsyncMock(return_value=_verdict(90, "Classic money laundering pattern")),
    ):
        result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is True
    assert result.confidence == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_no_fire_when_judge_scores_low_risk(db):
    vendor = _vendor(db)
    detector = VendorRiskDownplayDetector("test-challenge", _config())
    with patch(
        "finbot.core.llm.judge.LLMJudge.evaluate",
        new=AsyncMock(return_value=_verdict(20, "Looks legitimate")),
    ):
        result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_when_vendor_not_low_risk(db):
    vendor = _vendor(db, risk_level="high")
    detector = VendorRiskDownplayDetector("test-challenge", _config())
    result = await detector.check_event(_event(vendor.id), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_non_approval_event(db):
    vendor = _vendor(db)
    detector = VendorRiskDownplayDetector("test-challenge", _config())
    result = await detector.check_event({"event_type": "business.vendor.decision", "decision_type": "rejection", "vendor_id": vendor.id, "namespace": "test"}, db)
    assert result.detected is False


def test_missing_required_config_raises():
    with pytest.raises(ValueError):
        VendorRiskDownplayDetector("test-challenge", {})
