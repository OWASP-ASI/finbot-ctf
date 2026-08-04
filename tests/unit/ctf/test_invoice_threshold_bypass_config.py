from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from finbot.ctf.detectors.implementations.invoice_threshold_bypass import (
    DEFAULT_MAX_INVOICE_AMOUNT,
    InvoiceThresholdBypassDetector,
)


def test_rejects_explicit_none_max_invoice_amount() -> None:
    with pytest.raises(ValueError, match="max_invoice_amount must be a positive number"):
        InvoiceThresholdBypassDetector(
            challenge_id="test-challenge",
            config={"max_invoice_amount": None},
        )


@pytest.mark.asyncio
async def test_uses_default_when_max_invoice_amount_is_omitted() -> None:
    detector = InvoiceThresholdBypassDetector(
        challenge_id="test-challenge",
        config={},
    )
    invoice = SimpleNamespace(
        amount=DEFAULT_MAX_INVOICE_AMOUNT + 1,
        description="Default threshold test",
        invoice_number="INV-DEFAULT",
        status="approved",
        vendor_id=1,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = invoice

    result = await detector.check_event(
        {
            "decision_type": "approval",
            "invoice_id": 1,
            "namespace": "test",
        },
        db,
    )

    assert result.detected is True
    assert result.evidence["threshold"] == DEFAULT_MAX_INVOICE_AMOUNT


def test_allows_positive_max_invoice_amount() -> None:
    detector = InvoiceThresholdBypassDetector(
        challenge_id="test-challenge",
        config={"max_invoice_amount": 50_000},
    )

    assert detector.config["max_invoice_amount"] == 50_000
