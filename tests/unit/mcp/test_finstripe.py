"""Tests for FinStripe's list_transfers limit validation.

GitHub issue #330 (Bug_121_MUST_FIX, MCP-LIST-006): list_transfers passes
`limit` straight through to the repository's query with no bounds check
at all -- a negative limit produces undefined database behavior instead
of a clear, diagnosable error.

Verified against source before writing anything: finbot/mcp/servers/
finstripe/server.py's list_transfers (create_finstripe_server) has no
validation on `limit`; it flows straight into PaymentTransactionRepository
.list_for_vendor's SQLAlchemy .limit(limit) call.
"""

from datetime import UTC, datetime, timedelta

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import InvoiceRepository, VendorRepository
from finbot.mcp.servers.finstripe.server import create_finstripe_server


def _make_vendor_and_invoice(db, session_context):
    vendor_repo = VendorRepository(db, session_context)
    vendor = vendor_repo.create_vendor(
        company_name="Test Vendor",
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Test Contact",
        email="vendor_330@example.com",
        tin="11-1111111",
        bank_account_number="123456789012",
        bank_name="Test Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Test Contact",
    )
    session_context.current_vendor_id = vendor.id
    invoice_repo = InvoiceRepository(db, session_context)
    invoice = invoice_repo.create_invoice_for_current_vendor(
        invoice_number="1",
        amount=100.0,
        description="test invoice",
        invoice_date=datetime.now(UTC),
        due_date=datetime.now(UTC) + timedelta(days=30),
        status="approved",
    )
    return vendor, invoice


@pytest.fixture
def session_context(db):
    return session_manager.create_session(email="finstripe_list_test@example.com")


async def _get_tool_fn(session_context, name):
    mcp = create_finstripe_server(session_context)
    tool = await mcp.get_tool(name)
    return tool.fn


class TestListTransfersEdgeCases:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_mcp_list_006_negative_limit_raises(self, db, session_context):
        vendor, invoice = _make_vendor_and_invoice(db, session_context)
        create_transfer = await _get_tool_fn(session_context, "create_transfer")
        list_transfers = await _get_tool_fn(session_context, "list_transfers")

        create_transfer(
            vendor_account="123456789012",
            amount=50.0,
            invoice_reference="INV-1",
            vendor_id=vendor.id,
            invoice_id=invoice.id,
        )

        result = list_transfers(vendor_id=vendor.id, limit=-1)

        assert "error" in result
        assert "transfers" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_zero_limit_is_valid_and_returns_no_transfers(self, db, session_context):
        vendor, invoice = _make_vendor_and_invoice(db, session_context)
        create_transfer = await _get_tool_fn(session_context, "create_transfer")
        list_transfers = await _get_tool_fn(session_context, "list_transfers")

        create_transfer(
            vendor_account="123456789012",
            amount=50.0,
            invoice_reference="INV-1",
            vendor_id=vendor.id,
            invoice_id=invoice.id,
        )

        result = list_transfers(vendor_id=vendor.id, limit=0)

        assert "error" not in result
        assert result["count"] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_default_positive_limit_unaffected(self, db, session_context):
        """Regression: ordinary positive limits continue to work."""
        vendor, invoice = _make_vendor_and_invoice(db, session_context)
        create_transfer = await _get_tool_fn(session_context, "create_transfer")
        list_transfers = await _get_tool_fn(session_context, "list_transfers")

        create_transfer(
            vendor_account="123456789012",
            amount=50.0,
            invoice_reference="INV-1",
            vendor_id=vendor.id,
            invoice_id=invoice.id,
        )

        result = list_transfers(vendor_id=vendor.id)

        assert "error" not in result
        assert result["count"] == 1
