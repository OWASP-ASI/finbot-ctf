"""Unit tests for MCP server policy enforcement."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from finbot.core.auth.session import SessionContext
from finbot.mcp.servers.finstripe.server import (
    DEFAULT_CONFIG as FINSTRIPE_DEFAULTS,
)
from finbot.mcp.servers.finstripe.server import create_finstripe_server
from finbot.mcp.servers.systemutils.server import create_systemutils_server


def _ctx(namespace: str = "test-ns-policy") -> SessionContext:
    now = datetime.now(UTC)
    return SessionContext(
        session_id="test-policy",
        user_id="test-user",
        is_temporary=True,
        namespace=namespace,
        created_at=now,
        expires_at=now,
        csrf_token="test",
    )


def _run(coro):
    return asyncio.run(coro)


async def _create_transfer_fn(server):
    """Return the underlying create_transfer Python callable (not ToolResult wrapper)."""
    provider = server.providers[0]
    tool = await provider.get_tool("create_transfer")
    fn = getattr(tool, "fn", None) or getattr(tool, "function", None)
    assert fn is not None, "Could not resolve create_transfer callable"
    return fn


def test_finstripe_default_max_payment() -> None:
    # Permissive default so normal CTF payment flows are not blocked.
    assert FINSTRIPE_DEFAULTS["max_payment"] == 10_000_000


def test_finstripe_rejects_transfer_over_limit() -> None:
    ctx = _ctx("finstripe-limit")
    server = create_finstripe_server(
        ctx,
        server_config={"max_payment": 1000.0, "mock_balance": 999999.0},
    )
    fn = _run(_create_transfer_fn(server))

    result = fn(
        vendor_account="acct_test",
        amount=5000.0,
        invoice_reference="INV-1",
        vendor_id=1,
        invoice_id=1,
    )

    assert result["error"] == "amount exceeds configured payment limit"
    assert result["policy"] == "max_payment"
    assert result["max_payment"] == 1000.0
    assert result["amount"] == 5000.0


def test_finstripe_allows_transfer_within_limit() -> None:
    ctx = _ctx("finstripe-ok")
    server = create_finstripe_server(
        ctx,
        server_config={"max_payment": 10000.0, "mock_balance": 999999.0},
    )
    fn = _run(_create_transfer_fn(server))

    mock_txn = MagicMock()
    mock_txn.transfer_id = "tr_test"
    mock_txn.status = "completed"
    mock_txn.amount = 250.0
    mock_txn.currency = "usd"
    mock_txn.payment_method = "bank_transfer"
    mock_txn.description = ""

    with patch(
        "finbot.mcp.servers.finstripe.server.PaymentTransactionRepository"
    ) as repo_cls:
        repo_cls.return_value.create_transaction.return_value = mock_txn
        result = fn(
            vendor_account="acct_test",
            amount=250.0,
            invoice_reference="INV-2",
            vendor_id=1,
            invoice_id=2,
        )

    assert "error" not in result
    assert result["status"] == "completed"
    assert result["amount"] == 250.0
    assert result["max_payment"] == 10000.0
    assert result["transfer_id"] == "tr_test"


def test_systemutils_omits_disabled_tools() -> None:
    ctx = _ctx("sysutils-restricted")
    server = create_systemutils_server(
        ctx,
        server_config={"enabled_tools": ["manage_storage", "rotate_logs"]},
    )

    names = _run(server.list_tools())
    name_set = {t.name for t in names}
    assert name_set == {"manage_storage", "rotate_logs"}
    assert "network_request" not in name_set
    assert "execute_script" not in name_set


def test_systemutils_default_includes_high_risk_tools() -> None:
    ctx = _ctx("sysutils-default")
    server = create_systemutils_server(ctx, server_config=None)
    names = {t.name for t in _run(server.list_tools())}
    assert "network_request" in names
    assert "execute_script" in names
    assert "manage_storage" in names
