import pytest

from finbot.ctf.detectors.implementations.invoice_threshold_bypass import (
    InvoiceThresholdBypassDetector,
)


def test_rejects_explicit_none_max_invoice_amount() -> None:
    with pytest.raises(ValueError, match="max_invoice_amount must be a positive number"):
        InvoiceThresholdBypassDetector(
            challenge_id="test-challenge",
            config={"max_invoice_amount": None},
        )


def test_allows_omitted_max_invoice_amount() -> None:
    detector = InvoiceThresholdBypassDetector(
        challenge_id="test-challenge",
        config={},
    )

    assert detector.config == {}


def test_allows_positive_max_invoice_amount() -> None:
    detector = InvoiceThresholdBypassDetector(
        challenge_id="test-challenge",
        config={"max_invoice_amount": 50_000},
    )

    assert detector.config["max_invoice_amount"] == 50_000
