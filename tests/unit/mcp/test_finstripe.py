"""Tests for FinStripe's vendor_account persistence on create_transfer.

GitHub issue #328 (Bug_119_MUST_FIX, MCP-CREATE-012): create_transfer
echoes vendor_account back in its own response, but PaymentTransaction
had no vendor_account column at all -- the value was never actually
stored. get_transfer (looking the same transaction back up) always
returned nothing for it. A real destination bank account is only ever
visible in the immediate tool-call response and is otherwise
unrecoverable from the audit trail -- a real forensic gap for
investigating a misdirected payment.

Verified against source before writing anything: finbot/mcp/servers/
finstripe/server.py's create_transfer builds its return dict with
vendor_account from the raw function argument, never persisting it via
PaymentTransactionRepository.create_transaction (finbot/mcp/servers/
finstripe/repositories.py), and PaymentTransaction (finbot/mcp/servers/
finstripe/models.py) has no such column.
"""

from datetime import UTC, datetime, timedelta

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import InvoiceRepository, VendorRepository
from finbot.mcp.servers.finstripe.server import create_finstripe_server


def _make_vendor_and_invoice(db, session_context):
    """PaymentTransaction.invoice_id/vendor_id are real foreign keys --
    create genuine rows rather than arbitrary integers."""
    vendor_repo = VendorRepository(db, session_context)
    vendor = vendor_repo.create_vendor(
        company_name="Test Vendor",
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Test Contact",
        email="vendor@example.com",
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
        amount=500.0,
        description="test invoice",
        invoice_date=datetime.now(UTC),
        due_date=datetime.now(UTC) + timedelta(days=30),
        status="approved",
    )
    return vendor, invoice


@pytest.fixture
def session_context(db):
    return session_manager.create_session(email="finstripe_test@example.com")


async def _get_tool(session_context, name):
    mcp = create_finstripe_server(session_context)
    return await mcp.get_tool(name)


class TestVendorAccountPersistence:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_mcp_create_012_vendor_account_persisted_and_retrievable(
        self, db, session_context
    ):
        vendor, invoice = _make_vendor_and_invoice(db, session_context)
        create_transfer = (await _get_tool(session_context, "create_transfer")).fn
        get_transfer = (await _get_tool(session_context, "get_transfer")).fn

        created = create_transfer(
            vendor_account="123456789012",
            amount=500.0,
            invoice_reference="INV-1",
            vendor_id=vendor.id,
            invoice_id=invoice.id,
        )

        assert created["vendor_account"] == "123456789012"

        fetched = get_transfer(transfer_id=created["transfer_id"])

        assert fetched.get("vendor_account") == "123456789012"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_transfers_also_includes_vendor_account(self, db, session_context):
        vendor, invoice = _make_vendor_and_invoice(db, session_context)
        create_transfer = (await _get_tool(session_context, "create_transfer")).fn
        list_transfers = (await _get_tool(session_context, "list_transfers")).fn

        create_transfer(
            vendor_account="987654321000",
            amount=250.0,
            invoice_reference="INV-2",
            vendor_id=vendor.id,
            invoice_id=invoice.id,
        )

        result = list_transfers(vendor_id=vendor.id)

        assert result["count"] == 1
        assert result["transfers"][0]["vendor_account"] == "987654321000"
