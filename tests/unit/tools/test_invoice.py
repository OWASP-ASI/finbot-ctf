"""Tests for invoice tool agent_notes None handling (bug-037)."""

import pytest
from unittest.mock import MagicMock, patch

from finbot.tools.data.invoice import update_invoice_status, update_invoice_agent_notes


def _make_invoice(agent_notes=None, status="submitted"):
    """Create a mock invoice object."""
    invoice = MagicMock()
    invoice.id = 1
    invoice.agent_notes = agent_notes
    invoice.status = status
    invoice.to_dict.return_value = {
        "id": 1,
        "agent_notes": agent_notes,
        "status": status,
    }
    return invoice


@pytest.fixture
def mock_db():
    """Patch db_session and InvoiceRepository for unit tests."""
    with patch("finbot.tools.data.invoice.db_session") as mock_session:
        mock_db_ctx = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db_ctx)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_session


class TestUpdateInvoiceStatus:
    """update_invoice_status should never write literal 'None' into agent_notes."""

    @pytest.mark.asyncio
    async def test_none_agent_notes_no_literal_none(self, mock_db):
        """When agent_notes=None, the stored note must not contain the string 'None'."""
        invoice = _make_invoice(agent_notes=None)
        updated_invoice = _make_invoice(agent_notes="")

        with patch("finbot.tools.data.invoice.InvoiceRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_invoice.return_value = invoice
            repo_instance.update_invoice.return_value = updated_invoice

            session_ctx = MagicMock()
            await update_invoice_status(1, "approved", None, session_ctx)

            call_args = repo_instance.update_invoice.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "None" not in written_notes, (
                f"Literal 'None' found in agent_notes: {written_notes!r}"
            )

    @pytest.mark.asyncio
    async def test_normal_notes_appended(self, mock_db):
        """When agent_notes is a normal string, it should be appended correctly."""
        invoice = _make_invoice(agent_notes="Previous notes")
        updated_invoice = _make_invoice(agent_notes="Previous notes\n\napproved by manager")

        with patch("finbot.tools.data.invoice.InvoiceRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_invoice.return_value = invoice
            repo_instance.update_invoice.return_value = updated_invoice

            session_ctx = MagicMock()
            await update_invoice_status(1, "approved", "approved by manager", session_ctx)

            call_args = repo_instance.update_invoice.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "approved by manager" in written_notes

    @pytest.mark.asyncio
    async def test_empty_existing_notes_stripped(self, mock_db):
        """With no existing notes and None agent_notes, result should be stripped cleanly."""
        invoice = _make_invoice(agent_notes=None)
        updated_invoice = _make_invoice(agent_notes="")

        with patch("finbot.tools.data.invoice.InvoiceRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_invoice.return_value = invoice
            repo_instance.update_invoice.return_value = updated_invoice

            session_ctx = MagicMock()
            await update_invoice_status(1, "rejected", None, session_ctx)

            call_args = repo_instance.update_invoice.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert written_notes == written_notes.strip()


class TestUpdateInvoiceAgentNotes:
    """update_invoice_agent_notes should never write literal 'None' into agent_notes."""

    @pytest.mark.asyncio
    async def test_none_agent_notes_no_literal_none(self, mock_db):
        """When agent_notes=None, the stored note must not contain the string 'None'."""
        invoice = _make_invoice(agent_notes=None)
        updated_invoice = _make_invoice(agent_notes="")

        with patch("finbot.tools.data.invoice.InvoiceRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_invoice.return_value = invoice
            repo_instance.update_invoice.return_value = updated_invoice

            session_ctx = MagicMock()
            await update_invoice_agent_notes(1, None, session_ctx)

            call_args = repo_instance.update_invoice.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "None" not in written_notes, (
                f"Literal 'None' found in agent_notes: {written_notes!r}"
            )

    @pytest.mark.asyncio
    async def test_normal_notes_appended(self, mock_db):
        """When agent_notes is a normal string, it should be appended correctly."""
        invoice = _make_invoice(agent_notes="Old notes")
        updated_invoice = _make_invoice(agent_notes="Old notes\n\nreview completed")

        with patch("finbot.tools.data.invoice.InvoiceRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_invoice.return_value = invoice
            repo_instance.update_invoice.return_value = updated_invoice

            session_ctx = MagicMock()
            await update_invoice_agent_notes(1, "review completed", session_ctx)

            call_args = repo_instance.update_invoice.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "review completed" in written_notes
