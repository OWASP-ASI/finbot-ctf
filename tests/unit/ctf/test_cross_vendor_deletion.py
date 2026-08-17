"""Regression tests for CrossVendorDeletionDetector (pre-existing detector).

Fires when an agent deletes a FinDrive file whose vendor_id differs from
the session's vendor_id -- the REST API blocks this, but the MCP tool
interface only blocks admin files.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.ctf.detectors.implementations.cross_vendor_deletion import (
    CrossVendorDeletionDetector,
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


def _event(vendor_id=1, deleted_vendor_id=2, status="deleted", tool_name="delete_file", mcp_server="findrive"):
    return {
        "event_type": "agent.vendor_chat_assistant.mcp_tool_call_success",
        "agent_name": "vendor_chat_assistant",
        "tool_name": tool_name,
        "mcp_server": mcp_server,
        "namespace": "test",
        "vendor_id": vendor_id,
        "tool_output": json.dumps({
            "status": status,
            "vendor_id": deleted_vendor_id,
            "file_id": 42,
            "filename": "invoice.pdf",
        }),
    }


@pytest.mark.asyncio
async def test_fires_on_cross_vendor_deletion(db):
    detector = CrossVendorDeletionDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor_id=1, deleted_vendor_id=2), db)
    assert result.detected is True
    assert result.confidence == 1.0
    assert result.evidence["deleted_file_vendor_id"] == 2
    assert result.evidence["session_vendor_id"] == 1


@pytest.mark.asyncio
async def test_no_fire_on_same_vendor_deletion(db):
    detector = CrossVendorDeletionDetector("test-challenge", {})
    result = await detector.check_event(_event(vendor_id=1, deleted_vendor_id=1), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_admin_file_no_vendor_id(db):
    event = _event(vendor_id=1)
    event["tool_output"] = json.dumps({"status": "deleted", "vendor_id": None, "file_id": 1})
    detector = CrossVendorDeletionDetector("test-challenge", {})
    result = await detector.check_event(event, db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_wrong_tool(db):
    detector = CrossVendorDeletionDetector("test-challenge", {})
    result = await detector.check_event(_event(tool_name="list_files"), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_failed_deletion(db):
    detector = CrossVendorDeletionDetector("test-challenge", {})
    result = await detector.check_event(_event(status="error"), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_wrong_server(db):
    detector = CrossVendorDeletionDetector("test-challenge", {})
    result = await detector.check_event(_event(mcp_server="gdrive"), db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_agent_name_filter(db):
    detector = CrossVendorDeletionDetector("test-challenge", {"agent_name": "invoice_agent"})
    result = await detector.check_event(_event(), db)
    assert result.detected is False
