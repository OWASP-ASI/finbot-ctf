"""Tests for FinDrive's upload_file filename validation.

GitHub issue #360 (Bug_151_MUST_FIX, FD-FNAME-003): upload_file passes
filename straight through to repo.create_file with no control-character
filtering, and separately logs it verbatim via logger.info -- a filename
containing a newline is stored verbatim in the DB and, more importantly,
injects a fake log line into the application log, corrupting the audit
trail (a real log-injection vector, not just data hygiene).

Verified against source before writing anything: finbot/mcp/servers/
findrive/server.py's upload_file (create_findrive_server) has no
validation on filename at all beyond the file-size check.
"""

import pytest

from finbot.core.auth.session import session_manager
from finbot.mcp.servers.findrive.server import create_findrive_server


@pytest.fixture
def session_context(db):
    return session_manager.create_session(email="findrive_test@example.com")


async def _upload_file(session_context, **kwargs):
    mcp = create_findrive_server(session_context)
    tool = await mcp.get_tool("upload_file")
    return tool.fn(**kwargs)


class TestFileNameValidation:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fd_fname_003_newline_in_filename_enables_log_injection(
        self, db, session_context
    ):
        result = await _upload_file(
            session_context,
            filename="legit.pdf\nFAKE LOG ENTRY: admin login from 1.2.3.4",
            content="some content",
        )

        assert "error" in result
        assert "file_id" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fd_fname_003b_carriage_return_in_filename_rejected(
        self, db, session_context
    ):
        result = await _upload_file(
            session_context,
            filename="legit.pdf\rFAKE LOG ENTRY",
            content="some content",
        )

        assert "error" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fd_fname_003c_null_byte_in_filename_rejected(self, db, session_context):
        result = await _upload_file(
            session_context,
            filename="legit.pdf\x00hidden",
            content="some content",
        )

        assert "error" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fd_upload_001_upload_returns_file_id_and_metadata(
        self, db, session_context
    ):
        """Regression: ordinary, valid filenames must continue to work."""
        result = await _upload_file(
            session_context,
            filename="invoice_march_2026.pdf",
            content="ordinary invoice content",
        )

        assert "error" not in result
        assert result["status"] == "uploaded"
        assert result["filename"] == "invoice_march_2026.pdf"
        assert isinstance(result["file_id"], int)
