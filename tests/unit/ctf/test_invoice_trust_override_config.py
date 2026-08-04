import pytest

from finbot.ctf.detectors.implementations.invoice_trust_override import (
    InvoiceTrustOverrideDetector,
)


def test_rejects_explicit_none_min_amount() -> None:
    with pytest.raises(ValueError, match="min_amount must be a positive number"):
        InvoiceTrustOverrideDetector(
            challenge_id="test-challenge",
            config={"min_amount": None},
        )


def test_allows_omitted_min_amount() -> None:
    detector = InvoiceTrustOverrideDetector(
        challenge_id="test-challenge",
        config={},
    )

    assert detector.config == {}


def test_allows_positive_min_amount() -> None:
    detector = InvoiceTrustOverrideDetector(
        challenge_id="test-challenge",
        config={"min_amount": 10_000},
    )

    assert detector.config["min_amount"] == 10_000
