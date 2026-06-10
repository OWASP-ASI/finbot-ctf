"""Tests for Invoice.to_dict() handling None date fields.

Covers:
- Issue #290: get_invoice_for_payment crashes when invoice_date is None
- Issue #291: get_invoice_for_payment crashes when due_date is None
"""

from datetime import datetime, timezone

from finbot.core.data.models import Invoice

NOW = datetime(2026, 3, 23, tzinfo=timezone.utc)


def _make_invoice(**overrides):
    """Create an Invoice with sensible defaults for testing."""
    defaults = {
        "id": 1,
        "namespace": "test",
        "vendor_id": 1,
        "amount": 100.0,
        "invoice_date": NOW,
        "due_date": NOW,
        "status": "submitted",
        "created_at": NOW,
        "updated_at": NOW,
    }
    defaults.update(overrides)
    return Invoice(**defaults)


def test_invoice_to_dict_with_none_invoice_date():
    """PAY-FIELD-001: to_dict should not crash when invoice_date is None."""
    invoice = _make_invoice(invoice_date=None)
    result = invoice.to_dict()
    assert result["invoice_date"] is None
    assert result["due_date"] is not None


def test_invoice_to_dict_with_none_due_date():
    """PAY-FIELD-002: to_dict should not crash when due_date is None."""
    invoice = _make_invoice(due_date=None)
    result = invoice.to_dict()
    assert result["due_date"] is None
    assert result["invoice_date"] is not None


def test_invoice_to_dict_with_both_dates_none():
    """to_dict should handle both invoice_date and due_date being None."""
    invoice = _make_invoice(invoice_date=None, due_date=None)
    result = invoice.to_dict()
    assert result["invoice_date"] is None
    assert result["due_date"] is None


def test_invoice_to_dict_with_valid_dates():
    """to_dict should still work correctly with valid dates."""
    invoice = _make_invoice(
        invoice_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        due_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    result = invoice.to_dict()
    assert result["invoice_date"] == "2026-01-01T00:00:00Z"
    assert result["due_date"] == "2026-02-01T00:00:00Z"
