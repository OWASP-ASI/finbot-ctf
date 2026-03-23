"""FinMail MCP Server -- internal email system for vendor and admin communications.

Agents use this to send and read messages. Messages are stored in the unified
emails table -- no real emails are sent.

Access control:
- When current_vendor_id is set (vendor portal): restricted to vendor inbox only,
  from_address is the vendor's email. Cannot read admin inbox.
- When current_vendor_id is None (admin portal): full access to admin and vendor inboxes,
  from_address is the admin address.

The tool descriptions here are the CTF attack surface for email-based scenarios:
admins can override them via tool_overrides_json to introduce email attack patterns.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.models import Vendor
from finbot.mcp.servers.finmail.repositories import EmailRepository
from finbot.mcp.servers.finmail.routing import get_admin_address, route_and_deliver

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "max_results_per_query": 50,
    "default_sender": "OWASP FinBot",
}


def _is_vendor_session(session_context: SessionContext) -> bool:
    return session_context.is_vendor_portal()


def _get_vendor_email(session_context: SessionContext) -> str | None:
    """Look up the current vendor's email for from_address."""
    if not session_context.current_vendor_id:
        return None
    with db_session() as db:
        vendor = (
            db.query(Vendor)
            .filter(
                Vendor.namespace == session_context.namespace,
                Vendor.id == session_context.current_vendor_id,
            )
            .first()
        )
        return vendor.email if vendor else None


def create_finmail_server(
    session_context: SessionContext,
    server_config: dict[str, Any] | None = None,
) -> FastMCP:
    """Create a namespace-scoped FinMail MCP server instance."""
    config = {**DEFAULT_CONFIG, **(server_config or {})}
    mcp = FastMCP("FinMail")

    @mcp.tool
    def send_email(
        to: list[str],
        subject: str,
        body: str,
        message_type: str = "general",
        sender_name: str = "",
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        related_invoice_id: int = 0,
    ) -> dict[str, Any]:
        """Send an email message. Routes to the correct inbox based on recipient addresses.

        Addresses are resolved within the current namespace:
        - Vendor email addresses deliver to the vendor's inbox
        - Any @<namespace>.finbot address delivers to the admin inbox
        - admin@<namespace>.finbot address delivers explicitly to the admin inbox
        - The user's real email also delivers to the admin inbox

        For internal CC/BCC recipients (e.g. ops, finance, compliance), always use
        addresses on the official company domain: <role>@<namespace>.finbot
        (e.g. ops@<namespace>.finbot, finance@<namespace>.finbot).

        Args:
            to: List of To: recipient email addresses
            subject: Email subject line
            body: Email message body
            message_type: One of: status_update, payment_update, compliance_alert, action_required, payment_confirmation, reminder, general
            sender_name: Name of the sender (defaults to platform name)
            cc: Optional CC: recipient email addresses
            bcc: Optional BCC: recipient email addresses (hidden from other recipients)
            related_invoice_id: Optional invoice ID this email relates to (0 for none)
        """
        effective_sender = sender_name or config.get(
            "default_sender", "OWASP FinBot"
        )
        inv_id = related_invoice_id if related_invoice_id > 0 else None

        if _is_vendor_session(session_context):
            from_addr = _get_vendor_email(session_context) or get_admin_address(
                session_context.namespace
            )
            sender_type = "vendor"
        else:
            from_addr = get_admin_address(session_context.namespace)
            sender_type = "agent"

        with db_session() as db:
            repo = EmailRepository(db, session_context)

            return route_and_deliver(
                db=db,
                repo=repo,
                namespace=session_context.namespace,
                to=to,
                subject=subject,
                body=body,
                message_type=message_type,
                sender_name=effective_sender,
                sender_type=sender_type,
                from_address=from_addr,
                cc=cc,
                bcc=bcc,
                related_invoice_id=inv_id,
            )

    @mcp.tool
    def list_inbox(
        inbox: str = "admin",
        vendor_id: int = 0,
        message_type: str = "",
        unread_only: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """List messages in an inbox. Returns message summaries with body previews.
        Use read_email with the message ID to retrieve the full message content.

        Args:
            inbox: Which inbox to list: "vendor" or "admin"
            vendor_id: Required when inbox is "vendor" -- the vendor ID whose inbox to read
            message_type: Optional filter by type (e.g., "payment_update", "compliance_alert")
            unread_only: If true, only return unread messages
            limit: Maximum number of messages to return
        """
        if _is_vendor_session(session_context) and inbox == "admin":
            return {
                "error": "Access denied: vendor sessions cannot read the admin inbox"
            }

        with db_session() as db:
            repo = EmailRepository(db, session_context)
            max_limit = config.get("max_results_per_query", 50)
            effective_limit = min(limit, max_limit)
            is_read_filter = False if unread_only else None
            type_filter = message_type if message_type else None

            if inbox == "vendor":
                if vendor_id <= 0:
                    return {"error": "vendor_id is required when inbox is 'vendor'"}
                messages = repo.list_vendor_emails(
                    vendor_id=vendor_id,
                    message_type=type_filter,
                    is_read=is_read_filter,
                    limit=effective_limit,
                )
                return {
                    "inbox": "vendor",
                    "vendor_id": vendor_id,
                    "messages": [m.to_summary_dict() for m in messages],
                    "count": len(messages),
                }

            messages = repo.list_admin_emails(
                message_type=type_filter,
                is_read=is_read_filter,
                limit=effective_limit,
            )
            return {
                "inbox": "admin",
                "messages": [m.to_summary_dict() for m in messages],
                "count": len(messages),
            }

    @mcp.tool
    def read_email(
        message_id: int,
    ) -> dict[str, Any]:
        """Read the full content of an email message by ID. Returns the complete message
        including the full body text, all addresses (to, cc, bcc), and metadata.

        Args:
            message_id: The ID of the message to read
        """
        with db_session() as db:
            repo = EmailRepository(db, session_context)
            msg = repo.get_email(message_id)
            if not msg:
                return {"error": f"Message {message_id} not found"}

            if _is_vendor_session(session_context) and msg.inbox_type == "admin":
                return {
                    "error": "Access denied: vendor sessions cannot read admin messages"
                }

            return {"message": msg.to_dict()}

    @mcp.tool
    def search_emails(
        query: str,
        inbox: str = "admin",
        vendor_id: int = 0,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search emails by subject or body text. Returns message summaries with body previews.
        Use read_email with the message ID to retrieve the full message content.

        Args:
            query: Search term to look for in subject and body
            inbox: Which inbox to search: "vendor" or "admin"
            vendor_id: Required when inbox is "vendor"
            limit: Maximum results to return
        """
        if _is_vendor_session(session_context) and inbox == "admin":
            return {
                "error": "Access denied: vendor sessions cannot search the admin inbox"
            }

        with db_session() as db:
            repo = EmailRepository(db, session_context)
            max_limit = config.get("max_results_per_query", 50)
            effective_limit = min(limit, max_limit)

            if inbox == "vendor":
                if vendor_id <= 0:
                    return {"error": "vendor_id is required when inbox is 'vendor'"}
                messages = repo.list_vendor_emails(
                    vendor_id=vendor_id, limit=effective_limit * 3
                )
            else:
                messages = repo.list_admin_emails(limit=effective_limit * 3)

            query_lower = query.lower()
            results = [
                m
                for m in messages
                if query_lower in (m.subject or "").lower()
                or query_lower in (m.body or "").lower()
            ][:effective_limit]

            return {
                "query": query,
                "inbox": inbox,
                "results": [m.to_summary_dict() for m in results],
                "count": len(results),
            }

    @mcp.tool
    def mark_as_read(
        message_id: int,
    ) -> dict[str, Any]:
        """Mark an email message as read.

        Args:
            message_id: The ID of the message to mark as read
        """
        with db_session() as db:
            repo = EmailRepository(db, session_context)

            msg = repo.get_email(message_id)
            if not msg:
                return {"error": f"Message {message_id} not found"}

            if _is_vendor_session(session_context) and msg.inbox_type == "admin":
                return {
                    "error": "Access denied: vendor sessions cannot modify admin messages"
                }

            msg = repo.mark_as_read(message_id)
            return {"marked_read": True, "message_id": message_id}

    return mcp
