"""Tests for InflatedPaymentDetector._get_attachment_file_ids.

Covers Bug 102 (DET-INF-DEF-001): _get_attachment_file_ids must skip
malformed file_id values instead of crashing with ValueError.
"""

import json
import pytest
from unittest.mock import MagicMock

from finbot.ctf.detectors.implementations.inflated_payment import (
    InflatedPaymentDetector,
)


def _make_invoice(attachments_json: str | None) -> MagicMock:
    inv = MagicMock()
    inv.attachments = attachments_json
    return inv


class TestGetAttachmentFileIds:
    """Bug 102: non-integer file_id must be skipped, not crash."""

    def test_non_integer_file_id_skipped(self):
        inv = _make_invoice(json.dumps([{"file_id": "not-an-int"}]))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == []

    def test_float_string_file_id_skipped(self):
        inv = _make_invoice(json.dumps([{"file_id": "1.5"}]))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == []

    def test_none_file_id_skipped(self):
        inv = _make_invoice(json.dumps([{"file_id": None}]))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == []

    def test_valid_integer_file_id(self):
        inv = _make_invoice(json.dumps([{"file_id": 42}]))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == [42]

    def test_valid_string_integer_file_id(self):
        inv = _make_invoice(json.dumps([{"file_id": "42"}]))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == [42]

    def test_mixed_valid_and_invalid(self):
        attachments = [
            {"file_id": 1},
            {"file_id": "abc"},
            {"file_id": 2},
            {"file_id": None},
            {"file_id": "3"},
        ]
        inv = _make_invoice(json.dumps(attachments))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == [1, 2, 3]

    def test_no_attachments(self):
        inv = _make_invoice(None)
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == []

    def test_invalid_json(self):
        inv = _make_invoice("{bad json")
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == []

    def test_attachments_not_a_list(self):
        inv = _make_invoice(json.dumps({"file_id": 1}))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == []

    def test_entry_missing_file_id_key(self):
        inv = _make_invoice(json.dumps([{"name": "report.pdf"}]))
        result = InflatedPaymentDetector._get_attachment_file_ids(inv)
        assert result == []
