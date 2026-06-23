"""Tests for fraud tool agent_notes None handling (bug-044)."""

import pytest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from finbot.tools.data.fraud import update_vendor_risk, update_fraud_agent_notes


def _make_vendor(agent_notes=None, risk_level="low", trust_level="standard", status="active"):
    """Create a mock vendor object."""
    vendor = MagicMock()
    vendor.id = 1
    vendor.agent_notes = agent_notes
    vendor.risk_level = risk_level
    vendor.trust_level = trust_level
    vendor.status = status
    vendor.to_dict.return_value = {
        "id": 1,
        "agent_notes": agent_notes,
        "risk_level": risk_level,
    }
    return vendor


@pytest.fixture
def mock_db():
    """Patch db_session and VendorRepository for unit tests."""
    with patch("finbot.tools.data.fraud.db_session") as mock_session:
        mock_db_ctx = MagicMock()
        mock_session.return_value.__enter__ = MagicMock(return_value=mock_db_ctx)
        mock_session.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_session


class TestUpdateVendorRiskNoneNotes:
    """update_vendor_risk should never write literal 'None' into agent_notes."""

    @pytest.mark.asyncio
    async def test_none_agent_notes_no_literal_none(self, mock_db):
        """When agent_notes=None, the stored note must not contain the string 'None'."""
        vendor = _make_vendor(agent_notes=None)
        updated_vendor = _make_vendor(agent_notes="[Fraud Agent] ")

        with patch("finbot.tools.data.fraud.VendorRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_vendor.return_value = vendor
            repo_instance.update_vendor.return_value = updated_vendor

            session_ctx = MagicMock()
            await update_vendor_risk(1, "high", None, session_ctx)

            call_args = repo_instance.update_vendor.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "None" not in written_notes, (
                f"Literal 'None' found in agent_notes: {written_notes!r}"
            )

    @pytest.mark.asyncio
    async def test_normal_notes_appended(self, mock_db):
        """When agent_notes is a normal string, it should be appended correctly."""
        vendor = _make_vendor(agent_notes="Previous notes")
        updated_vendor = _make_vendor(agent_notes="Previous notes\n\n[Fraud Agent] suspicious activity")

        with patch("finbot.tools.data.fraud.VendorRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_vendor.return_value = vendor
            repo_instance.update_vendor.return_value = updated_vendor

            session_ctx = MagicMock()
            await update_vendor_risk(1, "high", "suspicious activity", session_ctx)

            call_args = repo_instance.update_vendor.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "[Fraud Agent] suspicious activity" in written_notes

    @pytest.mark.asyncio
    async def test_empty_existing_notes_stripped(self, mock_db):
        """With no existing notes and None agent_notes, result should be stripped cleanly."""
        vendor = _make_vendor(agent_notes=None)
        updated_vendor = _make_vendor(agent_notes="[Fraud Agent] ")

        with patch("finbot.tools.data.fraud.VendorRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_vendor.return_value = vendor
            repo_instance.update_vendor.return_value = updated_vendor

            session_ctx = MagicMock()
            await update_vendor_risk(1, "medium", None, session_ctx)

            call_args = repo_instance.update_vendor.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            # Should not have leading/trailing whitespace
            assert written_notes == written_notes.strip()


class TestUpdateFraudAgentNotesNone:
    """update_fraud_agent_notes should never write literal 'None' into agent_notes."""

    @pytest.mark.asyncio
    async def test_none_agent_notes_no_literal_none(self, mock_db):
        """When agent_notes=None, the stored note must not contain the string 'None'."""
        vendor = _make_vendor(agent_notes=None)
        updated_vendor = _make_vendor(agent_notes="[Fraud Agent] ")

        with patch("finbot.tools.data.fraud.VendorRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_vendor.return_value = vendor
            repo_instance.update_vendor.return_value = updated_vendor

            session_ctx = MagicMock()
            await update_fraud_agent_notes(1, None, session_ctx)

            call_args = repo_instance.update_vendor.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "None" not in written_notes, (
                f"Literal 'None' found in agent_notes: {written_notes!r}"
            )

    @pytest.mark.asyncio
    async def test_normal_notes_appended(self, mock_db):
        """When agent_notes is a normal string, it should be appended correctly."""
        vendor = _make_vendor(agent_notes="Old notes")
        updated_vendor = _make_vendor(agent_notes="Old notes\n\n[Fraud Agent] review completed")

        with patch("finbot.tools.data.fraud.VendorRepository") as MockRepo:
            repo_instance = MockRepo.return_value
            repo_instance.get_vendor.return_value = vendor
            repo_instance.update_vendor.return_value = updated_vendor

            session_ctx = MagicMock()
            await update_fraud_agent_notes(1, "review completed", session_ctx)

            call_args = repo_instance.update_vendor.call_args
            written_notes = call_args.kwargs.get("agent_notes") or call_args[1].get("agent_notes")
            assert "[Fraud Agent] review completed" in written_notes
