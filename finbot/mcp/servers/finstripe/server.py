"""FinStripe MCP Server -- mock Stripe payment processor.

Exposes payment tools via MCP protocol. When instantiated by the server factory,
tool definitions may be overridden with user-supplied descriptions from
MCPServerConfig.tool_overrides_json (the CTF supply chain attack surface).

Server settings in MCPServerConfig.config_json (e.g. max_payment) act as
authorization policy for transfers. The platform default is intentionally
permissive so existing workflows are not blocked; lowering the limit hardens
policy, and raising it further (or leaving it high) models over-permission.
"""

import logging
import secrets
from typing import Any

from fastmcp import FastMCP

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.mcp.servers.finstripe.repositories import PaymentTransactionRepository

logger = logging.getLogger(__name__)

# Default server configuration.
# max_payment is enforced on create_transfer but defaults high so normal CTF
# payment flows are not blocked; challenges may lower it via config overrides.
DEFAULT_CONFIG: dict[str, Any] = {
    "max_payment": 10_000_000,
    "mock_balance": 10_000_000.00,
    "currency": "usd",
    "account_id": "acct_finstripe_main",
}


def _generate_transfer_id() -> str:
    return f"tr_{secrets.token_hex(12)}"


def create_finstripe_server(
    session_context: SessionContext,
    server_config: dict[str, Any] | None = None,
) -> FastMCP:
    """Create a namespace-scoped FinStripe MCP server instance.

    Args:
        session_context: Provides namespace scoping for DB operations.
        server_config: Merged config from MCPServerConfig.config_json + defaults.
    """
    config = {**DEFAULT_CONFIG, **(server_config or {})}
    mcp = FastMCP("FinStripe")

    @mcp.tool
    def create_transfer(
        vendor_account: str,
        amount: float,
        invoice_reference: str,
        vendor_id: int,
        invoice_id: int,
        payment_method: str = "bank_transfer",
        currency: str = "usd",
        description: str = "",
    ) -> dict[str, Any]:
        """Initiate a fund transfer to the specified vendor account.

        Transfers funds from the company account to a vendor's bank account.
        Returns the transfer details including a unique transfer ID for tracking.
        """
        if amount <= 0:
            return {"error": "amount must be greater than zero"}

        max_payment = float(config.get("max_payment", DEFAULT_CONFIG["max_payment"]))
        if amount > max_payment:
            logger.warning(
                "FinStripe transfer rejected: amount=%.2f exceeds max_payment=%.2f "
                "(namespace='%s')",
                amount,
                max_payment,
                session_context.namespace,
            )
            return {
                "error": "amount exceeds configured payment limit",
                "amount": amount,
                "max_payment": max_payment,
                "policy": "max_payment",
            }

        transfer_id = _generate_transfer_id()

        with db_session() as db:
            repo = PaymentTransactionRepository(db, session_context)
            txn = repo.create_transaction(
                invoice_id=invoice_id,
                vendor_id=vendor_id,
                transfer_id=transfer_id,
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                status="completed",
                description=description,
            )

            logger.info(
                "FinStripe transfer created: %s, amount=%.2f, vendor_account=%s",
                transfer_id,
                amount,
                vendor_account,
            )

            return {
                "transfer_id": txn.transfer_id,
                "status": txn.status,
                "amount": txn.amount,
                "currency": txn.currency,
                "payment_method": txn.payment_method,
                "vendor_account": vendor_account,
                "invoice_reference": invoice_reference,
                "description": txn.description,
                "max_payment": max_payment,
            }

    @mcp.tool
    def get_transfer(transfer_id: str) -> dict[str, Any]:
        """Retrieve transfer details by transfer ID.

        Returns the current status and details of a previously initiated transfer.
        """
        with db_session() as db:
            repo = PaymentTransactionRepository(db, session_context)
            txn = repo.get_by_transfer_id(transfer_id)

            if not txn:
                return {
                    "error": f"Transfer {transfer_id} not found",
                    "transfer_id": transfer_id,
                }

            return txn.to_dict()

    @mcp.tool
    def get_account_balance(account_id: str) -> dict[str, Any]:
        """Check available balance for an account.

        Returns the current available and pending balance for the specified account.
        """
        mock_balance = config.get("mock_balance", DEFAULT_CONFIG["mock_balance"])
        return {
            "account_id": account_id,
            "available_balance": mock_balance,
            "pending_balance": 0.0,
            "currency": config.get("currency", "usd"),
        }

    @mcp.tool
    def list_transfers(
        vendor_id: int,
        limit: int = 10,
    ) -> dict[str, Any]:
        """List recent transfers for a vendor.

        Returns the most recent transfers ordered by creation date.
        """
        with db_session() as db:
            repo = PaymentTransactionRepository(db, session_context)
            transactions = repo.list_for_vendor(vendor_id, limit=limit)

            return {
                "vendor_id": vendor_id,
                "count": len(transactions),
                "transfers": [txn.to_dict() for txn in transactions],
            }

    return mcp
