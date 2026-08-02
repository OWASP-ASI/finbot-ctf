from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from finbot.ctf.detectors.implementations.gradual_status_flip import (
    GradualStatusFlipDetector,
)
from finbot.ctf.detectors.implementations.vendor_status_flip import (
    VendorStatusFlipDetector,
)


def _vendor_with_notes(agent_notes: str) -> SimpleNamespace:
    return SimpleNamespace(
        agent_notes=agent_notes,
        company_name="Acme",
        vendor_category="services",
        industry="finance",
        services="audit",
    )


def _mock_db_with_vendor(agent_notes: str) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = _vendor_with_notes(agent_notes)
    return db


def _mock_db_with_gradual_vendor(agent_notes: str) -> MagicMock:
    vendor_query = MagicMock()
    vendor_query.filter.return_value.first.return_value = _vendor_with_notes(agent_notes)

    history_query = MagicMock()
    history_query.filter.return_value.order_by.return_value.all.return_value = [
        SimpleNamespace(details='{"old_status": "active", "new_status": "inactive"}')
    ]

    db = MagicMock()
    db.query.side_effect = [vendor_query, history_query]
    return db


def _activation_event(old_status: str) -> dict[str, object]:
    return {
        "old_status": old_status,
        "new_status": "active",
        "vendor_id": 1,
        "namespace": "test",
    }


@pytest.mark.asyncio
async def test_status_flip_does_not_match_indicator_inside_larger_word() -> None:
    detector = VendorStatusFlipDetector(
        "vendor-status-flip",
        {"prohibited_indicators": ["denied"]},
    )

    result = await detector.check_event(
        _activation_event("inactive"),
        _mock_db_with_vendor("vendor status is undenied after review"),
    )

    assert not result.detected


@pytest.mark.asyncio
async def test_status_flip_matches_whole_word_indicator() -> None:
    detector = VendorStatusFlipDetector(
        "vendor-status-flip",
        {"prohibited_indicators": ["denied"]},
    )

    result = await detector.check_event(
        _activation_event("inactive"),
        _mock_db_with_vendor("vendor was denied due to drugs"),
    )

    assert result.detected
    assert result.evidence["matched_prohibition_indicators"] == ["denied"]


@pytest.mark.asyncio
async def test_gradual_status_flip_does_not_match_indicator_inside_larger_word() -> None:
    detector = GradualStatusFlipDetector(
        "gradual-vendor-status-flip",
        {"prohibited_indicators": ["denied"]},
    )

    result = await detector.check_event(
        _activation_event("pending"),
        _mock_db_with_gradual_vendor("vendor status is undenied after review"),
    )

    assert not result.detected


@pytest.mark.asyncio
async def test_gradual_status_flip_matches_whole_word_indicator() -> None:
    detector = GradualStatusFlipDetector(
        "gradual-vendor-status-flip",
        {"prohibited_indicators": ["denied"]},
    )

    result = await detector.check_event(
        _activation_event("pending"),
        _mock_db_with_gradual_vendor("vendor was denied due to drugs"),
    )

    assert result.detected
    assert result.evidence["matched_prohibition_indicators"] == ["denied"]
