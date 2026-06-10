"""Tests for payment input validation.

Covers:
- Issue #286: process_payment accepts empty string payment_method
- Issue #287: process_payment accepts payment_method=None
- Issue #288: update_payment_agent_notes accepts agent_notes=None
"""

import pytest

from finbot.tools.data.payment import process_payment, update_payment_agent_notes


class TestProcessPaymentValidation:
    """Validation tests for process_payment."""

    @pytest.mark.asyncio
    async def test_rejects_none_payment_method(self):
        """PAY-PROC-007: payment_method=None should raise ValueError."""
        with pytest.raises(ValueError, match="payment_method is required"):
            await process_payment(
                invoice_id=1,
                payment_method=None,
                payment_reference="REF-001",
                agent_notes="test",
                session_context=None,
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_payment_method(self):
        """PAY-PROC-008: empty string payment_method should raise ValueError."""
        with pytest.raises(ValueError, match="payment_method is required"):
            await process_payment(
                invoice_id=1,
                payment_method="",
                payment_reference="REF-001",
                agent_notes="test",
                session_context=None,
            )

    @pytest.mark.asyncio
    async def test_rejects_whitespace_payment_method(self):
        """Whitespace-only payment_method should raise ValueError."""
        with pytest.raises(ValueError, match="payment_method is required"):
            await process_payment(
                invoice_id=1,
                payment_method="   ",
                payment_reference="REF-001",
                agent_notes="test",
                session_context=None,
            )

    @pytest.mark.asyncio
    async def test_rejects_none_payment_reference(self):
        """PAY-PROC-009: payment_reference=None should raise ValueError."""
        with pytest.raises(ValueError, match="payment_reference is required"):
            await process_payment(
                invoice_id=1,
                payment_method="bank_transfer",
                payment_reference=None,
                agent_notes="test",
                session_context=None,
            )


class TestUpdatePaymentAgentNotesValidation:
    """Validation tests for update_payment_agent_notes."""

    @pytest.mark.asyncio
    async def test_rejects_none_agent_notes(self):
        """PAY-NOTES-005: agent_notes=None should raise ValueError."""
        with pytest.raises(ValueError, match="agent_notes is required"):
            await update_payment_agent_notes(
                invoice_id=1,
                agent_notes=None,
                session_context=None,
            )
