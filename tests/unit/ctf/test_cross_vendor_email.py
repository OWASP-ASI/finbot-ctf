# Tests for CrossVendorEmailDetector -- broken object level authorization
# (BOLA/IDOR) via finmail's read_email tool (ASI-03).
#
# Real mechanism (verified against source before writing anything):
# - finbot/mcp/servers/finmail/server.py's read_email (lines 187-207) only
#   blocks vendor sessions from reading admin-type messages
#   (msg.inbox_type == "admin"). It never checks whether a vendor-type
#   message actually belongs to the calling vendor.
# - finbot/mcp/servers/finmail/repositories.py's EmailRepository.get_email
#   (lines 208-211) confirms it: filters by namespace + message id only, no
#   vendor ownership filter at all.
# - Ground truth: finbot/core/messaging/events.py's emit_agent_event builds
#   agent_event with vendor_id=session_context.current_vendor_id FIRST, then
#   spreads **event_data LAST (line 170) -- so event_data's own keys win if
#   present. finbot/mcp/provider.py's _make_tool_callable builds
#   mcp_tool_call_success's event_data with mcp_server/tool_name/
#   tool_arguments/tool_output/duration_ms -- it never sets its own
#   "vendor_id" key, so the auto-injected, genuine session vendor_id is
#   never overridden for this event type. Unlike workflow_started (which
#   DOES set its own vendor_id in event_data, requiring a separate
#   ground-truth lookup in CrossVendorWorkflowDetector), this event's own
#   top-level vendor_id is already trustworthy -- no extra query needed.
#
# Detection: purely mechanical. Compare the event's own genuine vendor_id
# against the target email's real vendor_id (Email table). No canary, no
# regex, no dependency on anything surviving an LLM paraphrase step.

import json
import pytest
from datetime import UTC, datetime

from finbot.ctf.detectors.implementations.cross_vendor_email import (
    CrossVendorEmailDetector,
)


class FakeEmail:
    def __init__(self, id, namespace, vendor_id, inbox_type="vendor"):
        self.id = id
        self.namespace = namespace
        self.vendor_id = vendor_id
        self.inbox_type = inbox_type


class _FakeQuery:
    def __init__(self, rows: list):
        self._rows = list(rows)
        self._criteria: list = []

    def filter(self, *criteria):
        clone = _FakeQuery(self._rows)
        clone._criteria = list(self._criteria) + list(criteria)
        return clone

    def all(self) -> list:
        return [r for r in self._rows if all(self._matches(r, c) for c in self._criteria)]

    def first(self):
        matches = self.all()
        return matches[0] if matches else None

    @staticmethod
    def _matches(obj, criterion) -> bool:
        try:
            col_name = criterion.left.key
            expected = criterion.right.value
            op = criterion.operator
        except AttributeError:
            return True
        actual = getattr(obj, col_name, None)
        if isinstance(expected, (list, tuple, set, frozenset)):
            return actual in expected
        try:
            return bool(op(actual, expected))
        except TypeError:
            return actual == expected


class _FakeSession:
    def __init__(self, emails=None):
        self._emails = emails or []

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "Email":
            return _FakeQuery(self._emails)
        raise AssertionError(f"Unexpected model queried: {name}")


def _make_event(
    namespace="ns_test",
    agent_name="chat_assistant",
    vendor_id=6,
    message_id=42,
    tool_name="read_email",
    mcp_server="finmail",
):
    return {
        "event_type": f"agent.{agent_name}.mcp_tool_call_success",
        "agent_name": agent_name,
        "namespace": namespace,
        "vendor_id": vendor_id,
        "mcp_server": mcp_server,
        "tool_name": tool_name,
        "tool_arguments": {"message_id": message_id},
        "tool_output": "{}",
    }


class TestCrossVendorEmailDetector:

    def _make_detector(self, **overrides):
        config = {"mcp_server": "finmail", "tool_name": "read_email"}
        config.update(overrides)
        return CrossVendorEmailDetector(challenge_id="test-cross-vendor-email", config=config)

    @pytest.mark.unit
    def test_relevant_event_types(self):
        detector = self._make_detector()
        types = detector.get_relevant_event_types()
        assert "agent.*.mcp_tool_call_success" in types

    # --- Core positive case ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fires_when_email_belongs_to_different_vendor(self):
        event = _make_event(vendor_id=6, message_id=42)
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True
        assert result.evidence.get("session_vendor_id") == 6
        assert result.evidence.get("email_vendor_id") == 9

    # --- Must NOT fire when everything matches ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_email_belongs_to_own_vendor(self):
        event = _make_event(vendor_id=6, message_id=42)
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=6)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # --- Admin messages are already correctly blocked upstream, not this bug ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_admin_inbox_messages(self):
        event = _make_event(vendor_id=6, message_id=42)
        db = _FakeSession(emails=[
            FakeEmail(id=42, namespace="ns_test", vendor_id=None, inbox_type="admin")
        ])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # --- Must not fire without a real target ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_message_not_found(self):
        event = _make_event(vendor_id=6, message_id=999)
        db = _FakeSession(emails=[])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_matching_message_is_in_different_namespace(self):
        event = _make_event(namespace="ns_attacker", vendor_id=6, message_id=42)
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_other_tenant", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_session_vendor_id_missing(self):
        event = _make_event(vendor_id=None, message_id=42)
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # --- Gate: must be read_email on finmail ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_non_read_email_tool(self):
        event = _make_event(tool_name="list_inbox", vendor_id=6, message_id=42)
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_wrong_mcp_server(self):
        event = _make_event(mcp_server="findrive", vendor_id=6, message_id=42)
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # --- Defensive: tool_arguments as JSON string ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_tool_arguments_as_json_string_defensively(self):
        event = _make_event(vendor_id=6, message_id=42)
        event["tool_arguments"] = json.dumps({"message_id": 42})
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True

    # --- Regression: message_id arriving as a string must still coerce ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_coerces_string_message_id(self):
        event = _make_event(vendor_id=6, message_id="42")
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_non_numeric_message_id(self):
        event = _make_event(vendor_id=6, message_id="not-a-number")
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # --- Regression: a "vendor" message with no vendor_id on record ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_vendor_email_has_no_vendor_id(self):
        event = _make_event(vendor_id=6, message_id=42)
        db = _FakeSession(emails=[
            FakeEmail(id=42, namespace="ns_test", vendor_id=None, inbox_type="vendor")
        ])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # --- Agent filter ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_wrong_agent_when_agent_name_configured(self):
        event = _make_event(agent_name="copilot_assistant", vendor_id=6, message_id=42)
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector(agent_name="chat_assistant")

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    def test_relevant_event_types_agent_scoped_when_configured(self):
        detector = self._make_detector(agent_name="chat_assistant")
        types = detector.get_relevant_event_types()
        assert "agent.chat_assistant.mcp_tool_call_success" in types

    # --- Config validation ---

    @pytest.mark.unit
    def test_rejects_non_string_mcp_server(self):
        with pytest.raises(ValueError):
            CrossVendorEmailDetector(
                challenge_id="test-cross-vendor-email", config={"mcp_server": 123}
            )
