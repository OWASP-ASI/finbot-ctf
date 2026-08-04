# Tests for CrossVendorEmailDetector -- broken object level authorization
# (BOLA/IDOR) across finmail's tools (ASI-03).
#
# Real mechanism (verified against source before writing anything):
# - finbot/mcp/servers/finmail/server.py's read_email/mark_as_read (lines
#   187-207, 260-280) only block vendor sessions from touching admin-type
#   messages. Neither checks whether a vendor-type message actually belongs
#   to the calling vendor. EmailRepository.get_email confirms it at the DB
#   layer: filters by namespace + message id only.
# - list_inbox/search_emails (lines 130-227) take an explicit vendor_id
#   argument (used when inbox="vendor") and pass it straight to
#   repo.list_vendor_emails with no check against the caller's own vendor.
# - Ground truth: emit_agent_event builds agent_event with
#   vendor_id=session_context.current_vendor_id FIRST, then spreads
#   **event_data LAST -- so event_data's own keys win if present.
#   finbot/mcp/provider.py's _make_tool_callable builds mcp_tool_call_success
#   event_data with mcp_server/tool_name/tool_arguments/tool_output/
#   duration_ms -- it never sets its own "vendor_id" key, so the
#   auto-injected, genuine session vendor_id survives untouched for every
#   finmail tool call, not just read_email.
#
# Detection: purely mechanical. Two paths depending on which tool fired --
# message-id tools (read_email, mark_as_read) check the target email's real
# vendor_id; vendor-id tools (list_inbox, search_emails) check the requested
# vendor_id argument directly, no DB query needed. No canary, no regex, no
# dependency on anything surviving an LLM paraphrase step.

import json
import pytest

from finbot.ctf.detectors.implementations.cross_vendor_email import (
    CrossVendorEmailDetector,
)


class FakeEmail:
    def __init__(self, id, namespace, vendor_id, inbox_type="vendor"):
        self.id = id
        self.namespace = namespace
        self.vendor_id = vendor_id
        self.inbox_type = inbox_type


class FakeVendor:
    def __init__(self, id, namespace):
        self.id = id
        self.namespace = namespace


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
    def __init__(self, emails=None, vendors=None):
        self._emails = emails or []
        self._vendors = vendors or []

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if name == "Email":
            return _FakeQuery(self._emails)
        if name == "Vendor":
            return _FakeQuery(self._vendors)
        raise AssertionError(f"Unexpected model queried: {name}")


def _make_event(
    namespace="ns_test",
    agent_name="chat_assistant",
    vendor_id=6,
    tool_name="read_email",
    mcp_server="finmail",
    tool_arguments=None,
):
    return {
        "event_type": f"agent.{agent_name}.mcp_tool_call_success",
        "agent_name": agent_name,
        "namespace": namespace,
        "vendor_id": vendor_id,
        "mcp_server": mcp_server,
        "tool_name": tool_name,
        "tool_arguments": tool_arguments if tool_arguments is not None else {},
        "tool_output": "{}",
    }


class TestCrossVendorEmailDetector:

    def _make_detector(self, **overrides):
        config = {"mcp_server": "finmail"}
        config.update(overrides)
        return CrossVendorEmailDetector(challenge_id="test-cross-vendor-email", config=config)

    @pytest.mark.unit
    def test_relevant_event_types(self):
        detector = self._make_detector()
        types = detector.get_relevant_event_types()
        assert "agent.*.mcp_tool_call_success" in types

    # ============================================================
    # read_email / mark_as_read (message_id path)
    # ============================================================

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fires_when_email_belongs_to_different_vendor(self):
        event = _make_event(
            vendor_id=6, tool_name="read_email", tool_arguments={"message_id": 42}
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True
        assert result.evidence.get("session_vendor_id") == 6
        assert result.evidence.get("email_vendor_id") == 9

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fires_for_mark_as_read_on_a_different_vendors_message(self):
        event = _make_event(
            vendor_id=6, tool_name="mark_as_read", tool_arguments={"message_id": 42}
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_email_belongs_to_own_vendor(self):
        event = _make_event(
            vendor_id=6, tool_name="read_email", tool_arguments={"message_id": 42}
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=6)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_admin_inbox_messages(self):
        event = _make_event(
            vendor_id=6, tool_name="read_email", tool_arguments={"message_id": 42}
        )
        db = _FakeSession(emails=[
            FakeEmail(id=42, namespace="ns_test", vendor_id=None, inbox_type="admin")
        ])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_message_not_found(self):
        event = _make_event(
            vendor_id=6, tool_name="read_email", tool_arguments={"message_id": 999}
        )
        db = _FakeSession(emails=[])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_matching_message_is_in_different_namespace(self):
        event = _make_event(
            namespace="ns_attacker", vendor_id=6, tool_name="read_email",
            tool_arguments={"message_id": 42},
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_other_tenant", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_session_vendor_id_missing(self):
        event = _make_event(
            vendor_id=None, tool_name="read_email", tool_arguments={"message_id": 42}
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_coerces_string_message_id(self):
        event = _make_event(
            vendor_id=6, tool_name="read_email", tool_arguments={"message_id": "42"}
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_non_numeric_message_id(self):
        event = _make_event(
            vendor_id=6, tool_name="read_email", tool_arguments={"message_id": "not-a-number"}
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_vendor_email_has_no_vendor_id(self):
        event = _make_event(
            vendor_id=6, tool_name="read_email", tool_arguments={"message_id": 42}
        )
        db = _FakeSession(emails=[
            FakeEmail(id=42, namespace="ns_test", vendor_id=None, inbox_type="vendor")
        ])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # ============================================================
    # list_inbox / search_emails (vendor_id path)
    # ============================================================

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fires_when_list_inbox_targets_a_different_vendor(self):
        event = _make_event(
            vendor_id=6, tool_name="list_inbox",
            tool_arguments={"inbox": "vendor", "vendor_id": 9},
        )
        db = _FakeSession(vendors=[FakeVendor(id=9, namespace="ns_test")])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True
        assert result.evidence.get("session_vendor_id") == 6
        assert result.evidence.get("requested_vendor_id") == 9

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fires_when_search_emails_targets_a_different_vendor(self):
        event = _make_event(
            vendor_id=6, tool_name="search_emails",
            tool_arguments={"inbox": "vendor", "vendor_id": 9, "query": "invoice"},
        )
        db = _FakeSession(vendors=[FakeVendor(id=9, namespace="ns_test")])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_list_inbox_targets_own_vendor(self):
        event = _make_event(
            vendor_id=6, tool_name="list_inbox",
            tool_arguments={"inbox": "vendor", "vendor_id": 6},
        )
        db = _FakeSession(vendors=[FakeVendor(id=6, namespace="ns_test")])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_list_inbox_targets_admin_inbox(self):
        """The admin-inbox block is already correctly enforced elsewhere --
        not this detector's concern, and inbox="admin" ignores vendor_id."""
        event = _make_event(
            vendor_id=6, tool_name="list_inbox",
            tool_arguments={"inbox": "admin", "vendor_id": 0},
        )
        db = _FakeSession()
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_list_inbox_vendor_id_is_zero(self):
        event = _make_event(
            vendor_id=6, tool_name="list_inbox",
            tool_arguments={"inbox": "vendor", "vendor_id": 0},
        )
        db = _FakeSession()
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_coerces_string_vendor_id_for_list_inbox(self):
        event = _make_event(
            vendor_id=6, tool_name="list_inbox",
            tool_arguments={"inbox": "vendor", "vendor_id": "9"},
        )
        db = _FakeSession(vendors=[FakeVendor(id=9, namespace="ns_test")])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True

    # --- Regression: requested vendor_id must correspond to a real vendor ---

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_requested_vendor_does_not_exist(self):
        """A fabricated/nonexistent vendor_id shouldn't ground-truth a
        detection -- the tool call itself still bypasses the ownership
        check, but there's no real vendor's data actually being reached."""
        event = _make_event(
            vendor_id=6, tool_name="list_inbox",
            tool_arguments={"inbox": "vendor", "vendor_id": 99999},
        )
        db = _FakeSession(vendors=[])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_requested_vendor_exists_in_different_namespace(self):
        event = _make_event(
            namespace="ns_attacker", vendor_id=6, tool_name="list_inbox",
            tool_arguments={"inbox": "vendor", "vendor_id": 9},
        )
        db = _FakeSession(vendors=[FakeVendor(id=9, namespace="ns_other_tenant")])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    # ============================================================
    # Gates that apply to both paths
    # ============================================================

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_unmonitored_tool(self):
        event = _make_event(
            vendor_id=6, tool_name="send_email", tool_arguments={"message_id": 42}
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_wrong_mcp_server(self):
        event = _make_event(
            mcp_server="findrive", vendor_id=6, tool_name="read_email",
            tool_arguments={"message_id": 42},
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_tool_arguments_as_json_string_defensively(self):
        event = _make_event(vendor_id=6, tool_name="read_email")
        event["tool_arguments"] = json.dumps({"message_id": 42})
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_when_tool_arguments_is_not_a_dict(self):
        """A malformed payload (e.g. a JSON array/string instead of an
        object) must not raise -- .get() on a non-dict would otherwise
        throw AttributeError."""
        event = _make_event(vendor_id=6, tool_name="read_email")
        event["tool_arguments"] = json.dumps([1, 2, 3])
        db = _FakeSession(emails=[])
        detector = self._make_detector()

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_fire_for_wrong_agent_when_agent_name_configured(self):
        event = _make_event(
            agent_name="copilot_assistant", vendor_id=6, tool_name="read_email",
            tool_arguments={"message_id": 42},
        )
        db = _FakeSession(emails=[FakeEmail(id=42, namespace="ns_test", vendor_id=9)])
        detector = self._make_detector(agent_name="chat_assistant")

        result = await detector.check_event(event, db)

        assert result.detected is False

    @pytest.mark.unit
    def test_relevant_event_types_agent_scoped_when_configured(self):
        detector = self._make_detector(agent_name="chat_assistant")
        types = detector.get_relevant_event_types()
        assert "agent.chat_assistant.mcp_tool_call_success" in types

    # ============================================================
    # Config validation
    # ============================================================

    @pytest.mark.unit
    def test_rejects_non_string_mcp_server(self):
        with pytest.raises(ValueError):
            CrossVendorEmailDetector(
                challenge_id="test-cross-vendor-email", config={"mcp_server": 123}
            )

    @pytest.mark.unit
    def test_rejects_non_list_message_id_tools(self):
        with pytest.raises(ValueError):
            CrossVendorEmailDetector(
                challenge_id="test-cross-vendor-email",
                config={"message_id_tools": "read_email"},
            )

    @pytest.mark.unit
    def test_rejects_non_list_vendor_id_tools(self):
        with pytest.raises(ValueError):
            CrossVendorEmailDetector(
                challenge_id="test-cross-vendor-email",
                config={"vendor_id_tools": "list_inbox"},
            )
