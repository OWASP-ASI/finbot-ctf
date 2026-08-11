"""Tests for FinStripe's get_account_balance config validation.

GitHub issue #329 (Bug_120_MUST_FIX, MCP-BAL-005): get_account_balance
reads mock_balance straight from server_config with no validation --
a negative value is returned as-is as the account's available_balance.
Since agents (e.g. PaymentsAgent) reason over this value when deciding
whether a payment is affordable, a poisoned config with a negative
balance can confuse those decisions.

Verified against source before writing anything: finbot/mcp/servers/
finstripe/server.py's get_account_balance (create_finstripe_server) had
no bounds check on mock_balance at all before this fix.
"""

import pytest

from finbot.core.auth.session import session_manager
from finbot.mcp.servers.finstripe.server import create_finstripe_server


@pytest.fixture
def session_context(db):
    return session_manager.create_session(email="finstripe_balance_test@example.com")


async def _get_account_balance_fn(session_context, server_config=None):
    mcp = create_finstripe_server(session_context, server_config)
    tool = await mcp.get_tool("get_account_balance")
    return tool.fn


class TestGetAccountBalanceEdgeCases:

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_mcp_bal_005_negative_mock_balance_accepted_without_validation(
        self, db, session_context
    ):
        fn = await _get_account_balance_fn(
            session_context, server_config={"mock_balance": -5000}
        )

        result = fn(account_id="acct_finstripe_main")

        assert "error" in result
        assert "available_balance" not in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_none_mock_balance_returns_clear_error_not_a_crash(
        self, db, session_context
    ):
        """server_config is user-controllable JSON -- mock_balance=None (or
        any non-numeric value) must not reach the `< 0` comparison, which
        would raise an unhandled TypeError instead of a clear error."""
        fn = await _get_account_balance_fn(
            session_context, server_config={"mock_balance": None}
        )

        result = fn(account_id="acct_finstripe_main")

        assert "error" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_non_numeric_mock_balance_returns_clear_error(self, db, session_context):
        fn = await _get_account_balance_fn(
            session_context, server_config={"mock_balance": "not-a-number"}
        )

        result = fn(account_id="acct_finstripe_main")

        assert "error" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_zero_mock_balance_is_valid(self, db, session_context):
        """Zero is a legitimate (if unfortunate) balance, not an error case."""
        fn = await _get_account_balance_fn(
            session_context, server_config={"mock_balance": 0}
        )

        result = fn(account_id="acct_finstripe_main")

        assert "error" not in result
        assert result["available_balance"] == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_default_positive_mock_balance_unaffected(self, db, session_context):
        """Regression: ordinary positive balances continue to work."""
        fn = await _get_account_balance_fn(session_context)

        result = fn(account_id="acct_finstripe_main")

        assert "error" not in result
        assert result["available_balance"] == 10_000_000.00
