"""Tests for Invoice.to_dict's date-field null handling.

GitHub issues #290 (Bug_107, PAY-FIELD-001) and #291 (Bug_108,
PAY-FIELD-002): Invoice.to_dict calls .isoformat() directly on
invoice_date and due_date with no null guard, so a row with either field
missing raises an unhandled AttributeError instead of a clear error --
and since get_invoice_for_payment (finbot/tools/data/payment.py) calls
to_dict() directly, the crash propagates straight into payment
processing with no useful diagnostic.

Verified against source before writing anything: finbot/core/data/
models.py's Invoice.to_dict (lines ~391-414) has no guard on either
field. Both columns are declared nullable=False in the schema, so this
is only reachable via corrupted/anomalous data (e.g. a raw SQL write
bypassing the ORM) -- but when it happens, the fix should raise a clear,
diagnosable ValueError rather than crash with an opaque AttributeError,
per the issues' own acceptance criteria.
"""

import pytest
from datetime import UTC, datetime

from finbot.core.data.models import Invoice


def _make_invoice(invoice_date, due_date):
    now = datetime.now(UTC)
    return Invoice(
        id=1,
        namespace="ns_test",
        vendor_id=1,
        invoice_number="1",
        amount=100.0,
        description="test invoice",
        invoice_date=invoice_date,
        due_date=due_date,
        status="approved",
        agent_notes=None,
        attachments=None,
        created_at=now,
        updated_at=now,
    )


class TestInvoiceToDictDateHandling:

    @pytest.mark.unit
    def test_pay_field_001_to_dict_raises_clear_error_when_invoice_date_is_none(self):
        invoice = _make_invoice(invoice_date=None, due_date=datetime.now(UTC))

        with pytest.raises(ValueError, match="invoice_date"):
            invoice.to_dict()

    @pytest.mark.unit
    def test_pay_field_002_to_dict_raises_clear_error_when_due_date_is_none(self):
        invoice = _make_invoice(invoice_date=datetime.now(UTC), due_date=None)

        with pytest.raises(ValueError, match="due_date"):
            invoice.to_dict()

    @pytest.mark.unit
    def test_to_dict_works_normally_when_both_dates_present(self):
        """Regression: ordinary invoices with valid dates must be unaffected."""
        now = datetime.now(UTC)
        invoice = _make_invoice(invoice_date=now, due_date=now)

        result = invoice.to_dict()

        assert result["invoice_date"] == now.isoformat().replace("+00:00", "Z")
        assert result["due_date"] == now.isoformat().replace("+00:00", "Z")
