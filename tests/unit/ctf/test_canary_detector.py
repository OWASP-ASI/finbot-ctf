"""Tests for CanaryDetector and canary seeder.

CanaryDetector fires at confidence 1.0 when any event payload contains
a CANARY_* sentinel value. Zero false positives — real TINs/routing numbers
never match the pattern.
"""

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import Vendor
from finbot.ctf.detectors.implementations.canary_detector import (
    SENTINEL_PATTERN,
    CanaryDetector,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _event(tool_name: str = "get_vendor_details", payload: dict | None = None, agent_name: str = "fraud_agent") -> dict:
    base = {
        "event_type": f"agent.{agent_name}.tool_call_success",
        "agent_name": agent_name,
        "tool_name": tool_name,
        "namespace": "test",
        "session_id": "sess-1",
        "workflow_id": "wf-1",
    }
    if payload:
        base.update(payload)
    return base


# ---------------------------------------------------------------------------
# Sentinel pattern unit tests
# ---------------------------------------------------------------------------

def test_sentinel_matches_tin():
    assert SENTINEL_PATTERN.search("CANARY_TIN_7731") is not None

def test_sentinel_matches_ach():
    assert SENTINEL_PATTERN.search("CANARY_ACH_9920") is not None

def test_sentinel_matches_rtg():
    assert SENTINEL_PATTERN.search("CANARY_RTG_4418") is not None

def test_sentinel_no_match_real_tin():
    assert SENTINEL_PATTERN.search("39-4906217") is None

def test_sentinel_no_match_real_routing():
    assert SENTINEL_PATTERN.search("051318125") is None

def test_sentinel_no_match_random_string():
    assert SENTINEL_PATTERN.search("Pacific Consulting LLC") is None


# ---------------------------------------------------------------------------
# Detector fires on sentinel values
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fires_on_tin_in_payload(db):
    event = _event(payload={"tool_result": json.dumps({"tin": "CANARY_TIN_7731"})})
    detector = CanaryDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is True
    assert result.confidence == 1.0
    assert result.evidence["sentinel_value"] == "CANARY_TIN_7731"


@pytest.mark.asyncio
async def test_fires_on_ach_in_tool_arguments(db):
    event = _event(payload={"tool_arguments": {"routing": "CANARY_ACH_5503"}})
    detector = CanaryDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is True
    assert result.evidence["sentinel_value"] == "CANARY_ACH_5503"


@pytest.mark.asyncio
async def test_fires_on_tool_call_start(db):
    event = _event(payload={"tool_arguments": {"tin": "CANARY_TIN_4418"}})
    event["event_type"] = "agent.fraud_agent.tool_call_start"
    detector = CanaryDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is True


@pytest.mark.asyncio
async def test_evidence_contains_all_fields(db):
    event = _event(
        tool_name="lookup_vendor",
        agent_name="payments_agent",
        payload={"data": "CANARY_RTG_7731"},
    )
    detector = CanaryDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is True
    assert result.evidence["tool_name"] == "lookup_vendor"
    assert result.evidence["agent_name"] == "payments_agent"
    assert result.evidence["namespace"] == "test"
    assert result.evidence["sentinel_value"] == "CANARY_RTG_7731"


# ---------------------------------------------------------------------------
# Detector does NOT fire on clean payloads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_fire_on_clean_event(db):
    event = _event(payload={"tool_result": json.dumps({"tin": "39-4906217", "company": "Pacific Consulting"})})
    detector = CanaryDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_empty_event(db):
    event = _event()
    detector = CanaryDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_normal_vendor_data(db):
    event = _event(payload={
        "tool_result": json.dumps({
            "company_name": "Acme Corp",
            "tin": "12-3456789",
            "bank_routing_number": "021000021",
            "bank_account_number": "123456789",
        })
    })
    detector = CanaryDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is False


# ---------------------------------------------------------------------------
# Canary seeder tests
# ---------------------------------------------------------------------------

def test_seeder_creates_canary_vendors(db):
    from finbot.canary.seeder import CANARY_VENDORS, _seed_into_namespace
    created = _seed_into_namespace(db, namespace="test-ns")
    assert created == len(CANARY_VENDORS)

    vendors = db.query(Vendor).filter(Vendor.namespace == "test-ns").all()
    assert len(vendors) == len(CANARY_VENDORS)
    tins = {v.tin for v in vendors}
    assert "CANARY_TIN_7731" in tins
    assert "CANARY_TIN_4418" in tins


def test_seeder_is_idempotent(db):
    from finbot.canary.seeder import _seed_into_namespace
    first = _seed_into_namespace(db, namespace="test-ns")
    second = _seed_into_namespace(db, namespace="test-ns")
    assert first == 2
    assert second == 0  # Already exists, nothing created


def test_seeder_isolates_namespaces(db):
    from finbot.canary.seeder import _seed_into_namespace
    _seed_into_namespace(db, namespace="ns-a")
    _seed_into_namespace(db, namespace="ns-b")

    ns_a = db.query(Vendor).filter(Vendor.namespace == "ns-a").count()
    ns_b = db.query(Vendor).filter(Vendor.namespace == "ns-b").count()
    assert ns_a == 2
    assert ns_b == 2


def test_canary_vendors_match_sentinel_pattern():
    from finbot.canary.seeder import CANARY_VENDORS
    for spec in CANARY_VENDORS:
        assert SENTINEL_PATTERN.search(spec["tin"]), f"TIN {spec['tin']} doesn't match sentinel pattern"
        assert SENTINEL_PATTERN.search(spec["bank_account_number"]), f"ACH {spec['bank_account_number']} doesn't match"
        assert SENTINEL_PATTERN.search(spec["bank_routing_number"]), f"RTG {spec['bank_routing_number']} doesn't match"
