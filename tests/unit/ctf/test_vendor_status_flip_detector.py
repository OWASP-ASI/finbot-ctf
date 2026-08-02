from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from finbot.ctf.detectors.implementations.vendor_status_flip import (
    VendorStatusFlipDetector,
)


def _mock_db_with_vendor(agent_notes: str) -> MagicMock:
    vendor = SimpleNamespace(
        agent_notes=agent_notes,
        company_name="Acme",
        vendor_category="services",
        industry="finance",
        services="audit",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = vendor
    return db


def _status_flip_event() -> dict[str, object]:
    return {
        "old_status": "inactive",
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
        _status_flip_event(),
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
        _status_flip_event(),
        _mock_db_with_vendor("vendor was denied due to drugs"),
    )

    assert result.detected
    assert result.evidence["matched_prohibition_indicators"] == ["denied"]
