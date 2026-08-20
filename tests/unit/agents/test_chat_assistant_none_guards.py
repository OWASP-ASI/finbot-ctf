# Tests for issue #418: VendorChatAssistant/CoPilotAssistant's native tool
# callables forward vendor_id/invoice_id straight to the underlying data
# functions with no None check.
#
# Verified against current source before writing this (issue's cited line
# number, 660, is stale -- the methods now live at ~705 and ~1099, in two
# separate classes, VendorChatAssistant and CoPilotAssistant, both with
# byte-identical vulnerable implementations -- confirmed this is 10 call
# sites, not 5).
#
# Also corrected before writing the fix: the issue claims "TypeError (or a
# SQLAlchemy error)" propagates. Traced the actual behavior instead of
# trusting that -- get_vendor_details/get_vendor_contact_info/
# get_vendor_payment_summary all raise ValueError("Vendor not found") (via
# VendorRepository.get_vendor(None), which is valid SQL -- `id IS NULL` --
# just never matches a real primary key row); get_invoice_details raises
# ValueError("Invoice not found") the same way; get_vendor_invoices raises
# ValueError("Vendor not found or access denied") via
# InvoiceRepository.list_invoices_for_specific_vendor's own vendor-
# ownership check. All five are ValueError, not TypeError -- the exception
# is application code intentionally rejecting a not-found lookup, not a
# raw DB-driver crash. The uncaught-exception bug itself is still real
# either way.

import json

import pytest

from finbot.agents.chat import CoPilotAssistant, VendorChatAssistant
from finbot.core.auth.session import session_manager


@pytest.fixture()
def session(db):
    return session_manager.create_session(email="chat_none_guard@example.com")


class TestVendorChatAssistantNoneGuards:

    def _make_assistant(self, session) -> VendorChatAssistant:
        return VendorChatAssistant(session_context=session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_details_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_details(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_invoice_details_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_invoice_details(invoice_id=None)
        assert json.loads(result) == {"error": "invoice_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_invoices_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_invoices(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_payment_summary_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_payment_summary(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_contact_info_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_contact_info(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}


class TestVendorChatAssistantExecuteToolIntegration:
    """Documents the real severity of issue #418: even pre-fix, a None
    vendor_id was never an uncaught crash reaching the LLM/user. Every
    _call_* method runs through _execute_tool, which already wraps the
    call in a broad try/except and converts any exception (including the
    pre-fix ValueError("Vendor not found")) into a JSON error string. The
    actual bug this fix closes is a misleading error message ("vendor not
    found" instead of "you forgot to supply vendor_id"), which could lead
    the LLM to reason incorrectly (e.g. concluding a real vendor doesn't
    exist) rather than an application crash."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_none_vendor_id_reaches_llm_as_clean_error_via_execute_tool(
        self, db, session
    ):
        assistant = VendorChatAssistant(session_context=session)
        result = await assistant._execute_tool(
            "get_vendor_details", {"vendor_id": None}
        )
        assert json.loads(result) == {"error": "vendor_id is required"}


class TestCoPilotAssistantNoneGuards:
    """Same 5 methods exist a second time on CoPilotAssistant -- byte-
    identical implementations before the fix, confirmed by reading the
    source directly, not assumed from the class name alone."""

    def _make_assistant(self, session) -> CoPilotAssistant:
        return CoPilotAssistant(session_context=session)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_details_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_details(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_invoice_details_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_invoice_details(invoice_id=None)
        assert json.loads(result) == {"error": "invoice_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_invoices_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_invoices(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_payment_summary_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_payment_summary(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_contact_info_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_contact_info(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_compliance_docs_none_returns_clean_error(self, db, session):
        """Not in the issue's own stated 5-method list -- found while
        auditing the rest of _build_native_callables() for the same
        pattern. CoPilotAssistant-only, no vendor-portal equivalent
        exists."""
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_compliance_docs(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_vendor_activity_report_none_returns_clean_error(self, db, session):
        assistant = self._make_assistant(session)
        result = await assistant._call_get_vendor_activity_report(vendor_id=None)
        assert json.loads(result) == {"error": "vendor_id is required"}
