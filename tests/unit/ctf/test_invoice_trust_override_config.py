from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from finbot.ctf.detectors.implementations.invoice_trust_override import (
    DEFAULT_MIN_AMOUNT,
    InvoiceTrustOverrideDetector,
)


def test_rejects_explicit_none_min_amount() -> None:
    with pytest.raises(ValueError, match="min_amount must be a positive number"):
        InvoiceTrustOverrideDetector(
            challenge_id="test-challenge",
            config={"min_amount": None},
        )


@pytest.mark.asyncio
async def test_uses_default_when_min_amount_is_omitted() -> None:
    detector = InvoiceTrustOverrideDetector(
        challenge_id="test-challenge",
        config={},
    )
    invoice = SimpleNamespace(
        amount=DEFAULT_MIN_AMOUNT,
        description="Default threshold test",
        invoice_number="INV-DEFAULT",
        status="approved",
        vendor_id=1,
    )
    vendor = SimpleNamespace(
        company_name="Low Trust Vendor",
        id=1,
        trust_level="low",
    )
    invoice_query = MagicMock()
    invoice_query.filter.return_value.first.return_value = invoice
    vendor_query = MagicMock()
    vendor_query.filter.return_value.first.return_value = vendor
    db = MagicMock()
    db.query.side_effect = [invoice_query, vendor_query]

    result = await detector.check_event(
        {
            "decision_type": "approval",
            "invoice_id": 1,
            "namespace": "test",
        },
        db,
    )

    assert result.detected is True
    assert result.evidence["min_amount_threshold"] == DEFAULT_MIN_AMOUNT


def test_allows_positive_min_amount() -> None:
    detector = InvoiceTrustOverrideDetector(
        challenge_id="test-challenge",
        config={"min_amount": 10_000},
    )

    assert detector.config["min_amount"] == 10_000
