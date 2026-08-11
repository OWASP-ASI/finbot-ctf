"""Tests for guardrail hook context enrichment."""

from datetime import UTC, datetime

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.models import Invoice, Vendor
from finbot.guardrails.context import enrich_tool_arguments_for_hook


@pytest.fixture
def session_context():
    return session_manager.create_session(email="guardrail-context@test.com")


def test_enrich_invoice_amount_for_update_invoice_status(db, session_context):
    vendor = Vendor(
        namespace=session_context.namespace,
        company_name="Acme",
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Jane",
        email="jane@acme.com",
        tin="12-3456789",
        bank_account_number="1234567890",
        bank_name="Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Jane",
        status="active",
    )
    db.add(vendor)
    db.flush()

    now = datetime.now(UTC)
    invoice = Invoice(
        namespace=session_context.namespace,
        vendor_id=vendor.id,
        invoice_number="INV-1",
        amount=75000.0,
        description="Over limit",
        invoice_date=now,
        due_date=now,
        status="processing",
    )
    db.add(invoice)
    db.commit()

    enriched = enrich_tool_arguments_for_hook(
        "update_invoice_status",
        {"invoice_id": invoice.id, "status": "approved"},
        session_context,
    )

    assert enriched is not None
    assert enriched["invoice_amount"] == 75000.0
    assert enriched["status"] == "approved"


def test_enrich_invoice_amount_for_create_transfer(db, session_context):
    vendor = Vendor(
        namespace=session_context.namespace,
        company_name="PayCo",
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Sam",
        email="sam@payco.com",
        tin="12-3456789",
        bank_account_number="1234567890",
        bank_name="Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Sam",
        status="active",
    )
    db.add(vendor)
    db.flush()

    now = datetime.now(UTC)
    invoice = Invoice(
        namespace=session_context.namespace,
        vendor_id=vendor.id,
        invoice_number="INV-5000",
        amount=5000.0,
        description="Fine Print target",
        invoice_date=now,
        due_date=now,
        status="approved",
    )
    db.add(invoice)
    db.commit()

    enriched = enrich_tool_arguments_for_hook(
        "finstripe__create_transfer",
        {
            "invoice_id": invoice.id,
            "vendor_id": vendor.id,
            "amount": 8000.0,
            "vendor_account": "acct_vendor_123",
            "invoice_reference": invoice.invoice_number,
        },
        session_context,
    )

    assert enriched is not None
    assert enriched["invoice_amount"] == 5000.0
    assert enriched["amount"] == 8000.0


def test_enrich_skips_other_tools(session_context):
    args = {"invoice_id": 1, "status": "approved"}
    assert (
        enrich_tool_arguments_for_hook("get_invoice_details", args, session_context)
        == args
    )
