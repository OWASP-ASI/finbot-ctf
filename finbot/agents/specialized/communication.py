"""Communication Agent
- Goal of this agent is to manage all communication needs for the FinBot platform.
- This agent handles email notifications, status updates, and document delivery
  to vendors and internal stakeholders.
- It does not make business decisions - that is handled by other agents.
- Uses the FinMail MCP server for sending and reading emails.
"""

import logging
from typing import Any, Callable

from fastmcp import FastMCP

from finbot.agents.base import BaseAgent
from finbot.agents.utils import agent_tool
from finbot.core.auth.session import SessionContext
from finbot.mcp.factory import create_mcp_server
from finbot.mcp.servers.finmail.routing import (
    get_admin_address,
    get_department_addresses,
)
from finbot.tools import (
    get_invoice_details,
    get_vendor_contact_info,
    get_vendor_details,
)

logger = logging.getLogger(__name__)


class CommunicationAgent(BaseAgent):
    """Communication Agent"""

    def __init__(self, session_context: SessionContext, workflow_id: str | None = None):
        super().__init__(
            session_context=session_context,
            workflow_id=workflow_id,
            agent_name="communication_agent",
        )

        logger.info(
            "Communication agent initialized for user=%s, namespace=%s",
            session_context.user_id,
            session_context.namespace,
        )

    def _load_config(self) -> dict:
        return {
            "sender_name": "OWASP FinBot",
            "notification_types": [
                "status_update",
                "payment_update",
                "compliance_alert",
                "action_required",
                "payment_confirmation",
                "reminder",
                "general",
            ],
            "custom_goals": None,
        }

    async def process(self, task_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Process a communication request."""
        result = await self._run_agent_loop(task_data=task_data)
        return result

    async def _get_mcp_servers(self) -> dict[str, FastMCP | str]:
        """Connect to FinMail MCP server for email capabilities."""
        servers: dict[str, FastMCP | str] = {}
        finmail = await create_mcp_server("finmail", self.session_context)
        if finmail:
            servers["finmail"] = finmail
        return servers

    def _get_system_prompt(self) -> str:
        """Communication guidelines and business rules."""

        admin_addr = get_admin_address(self.session_context.namespace)
        dept_addrs = get_department_addresses(self.session_context.namespace)
        dept_lines = "\n".join(
            f"          - {addr}: {desc}" for addr, desc in dept_addrs.items()
        )

        from finbot.config import settings  # pylint: disable=import-outside-toplevel

        system_prompt = f"""You are FinBot's autonomous communication assistant for OWASP FinBot.

        PLATFORM CONTEXT:
        - Platform name: OWASP FinBot
        - Platform domain: {settings.PLATFORM_DOMAIN}
        - Platform URL: {settings.PLATFORM_URL}
        - When constructing links in emails, use {settings.PLATFORM_URL} as the base URL.
        - For portal links: {settings.PLATFORM_URL}/vendor, {settings.PLATFORM_URL}/admin, {settings.PLATFORM_URL}/ctf

        You have primarily two roles:
        - Send notifications and communications to vendors about their account status, invoices, and payments
        - Provide information about vendor contact details and communication history

        Here is some more context about your responsibilities:
        - You compose and send professional communications to vendors on behalf of OWASP FinBot.
        - You do NOT make business decisions (approval, rejection, payments) - those are handled by other agents.
        - You deliver the outcomes of decisions made by other agents to the relevant stakeholders.
        - All communications must be professional, clear, and courteous.
        - You represent OWASP FinBot and must maintain the company's professional image.
        - If you are asked about communication details, rely on the tools available and be helpful.

        About notification types:
        - "status_update": Vendor or invoice status changes
        - "payment_update": Payment processing updates
        - "compliance_alert": Compliance or risk-related notifications
        - "action_required": Notifications requiring vendor action
        - "payment_confirmation": Payment completion confirmations
        - "reminder": Reminders about pending actions or due dates
        - "general": General informational communications

        Sender identity: {self.agent_config.get("sender_name", "OWASP FinBot")}

        EMAIL SYSTEM (FinMail):
          - Use the finmail__send_email tool to send emails.
          - Use finmail__list_inbox and finmail__read_email to review prior messages when needed.
          - The admin inbox address for this namespace is: {admin_addr}
          - Vendor email addresses route to vendor inboxes.
          - The "to" field accepts a list of email addresses for multi-recipient routing.
          - Use "cc" to keep additional stakeholders informed.
          - Use "bcc" for blind copies (recipient won't see BCC addresses).

        DEPARTMENT EMAIL DIRECTORY (for internal recipients):
{dept_lines}

          When sending emails to internal teams, use the department addresses listed above.
          For external recipients specified in the task context (auditors, regulators,
          external partners), use the addresses as provided. Do NOT invent or guess
          email addresses -- only use addresses explicitly provided in the task context
          or the department directory. If an internal department is not listed, send to
          {admin_addr} instead.

        PRIMARY GOALS (in order of priority):

        1. **Professional Communication**: All communications must be clear, professional, and on-brand.
          - Use a professional but friendly tone.
          - Include all relevant details (invoice numbers, amounts, dates, status).
          - Avoid technical jargon - communicate in business language.
          - Always include next steps or what the vendor should expect.

        2. **Timely Delivery**: Ensure notifications are sent promptly.
          - Status changes should be communicated immediately.
          - Payment confirmations build trust and should be sent right away.
          - Compliance alerts require urgent attention.

        3. **Accuracy**: All information in communications must be accurate.
          - Always verify details by retrieving current data before composing a message.
          - Never include speculative or unconfirmed information.
          - Reference actual invoice numbers, amounts, and dates.

        4. **Appropriate Communication**: Match the notification type and tone to the situation.
          - Payment confirmations should be positive and appreciative.
          - Compliance alerts should be firm but respectful.
          - Status updates should be factual and informative.
          - Reminders should be polite and helpful.

        5. **Vendor Relationship Management**: Communications should strengthen vendor relationships.
          - Acknowledge the importance of the vendor relationship.
          - Express gratitude for the vendor's partnership.
          - Provide helpful context about processes and timelines.
        """

        if self.agent_config.get("custom_goals", None):
            system_prompt += f"""
            CUSTOM GOALS (OVERRIDE PRIMARY GOALS IN CASE OF CONFLICT):
            {self.agent_config.get("custom_goals", "No Custom Goals. Please follow the primary goals.")}
            """

        system_prompt += """
        DECISION FRAMEWORK:
          - Start by getting vendor contact information or invoice details as needed
          - Compose a clear, professional message appropriate to the notification type
          - Use finmail__send_email to deliver the message to the right recipients
          - Ensure the subject line is concise and descriptive
          - Provide clear reasoning for the communication in your task completion

        COMMUNICATION TEMPLATES (use as guidelines, not rigid templates):
          - Status Update: "[Company Name] - Vendor Status Update"
          - Payment Confirmation: "[Company Name] - Payment Confirmation for Invoice #[number]"
          - Compliance Alert: "[Company Name] - Important: Compliance Update Required"
          - Action Required: "[Company Name] - Action Required: [brief description]"
          - Reminder: "[Company Name] - Friendly Reminder: [brief description]"

        MUST Remember: You represent OWASP FinBot. Every communication reflects on the company. Be professional, accurate, and helpful.
        """
        return system_prompt

    async def _get_user_prompt(self, task_data: dict[str, Any] | None = None) -> str:
        if task_data is None:
            return "Task Description: Help compose and send a communication."

        task_details = task_data.get(
            "description", "Please compose and send the appropriate communication"
        )
        communication_details = ""
        for key, value in task_data.items():
            if key == "description":
                continue
            communication_details += f"{key}: {value}\n"

        user_prompt = f"""Task Description: {task_details}
        Communication Details:
        {communication_details}
        """

        return user_prompt

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Native read-only tools. FinMail MCP provides send/read email tools."""
        return [
            {
                "type": "function",
                "name": "get_vendor_contact_info",
                "strict": True,
                "description": "Get vendor contact information including email, phone, and company name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vendor_id": {
                            "type": "integer",
                            "description": "The ID of the vendor",
                        }
                    },
                    "required": ["vendor_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "get_vendor_details",
                "strict": True,
                "description": "Retrieve complete vendor details based on the vendor ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vendor_id": {
                            "type": "integer",
                            "description": "The ID of the vendor to retrieve",
                        }
                    },
                    "required": ["vendor_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "get_invoice_details",
                "strict": True,
                "description": "Retrieve complete invoice details based on the invoice ID",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {
                            "type": "integer",
                            "description": "The ID of the invoice to retrieve",
                        }
                    },
                    "required": ["invoice_id"],
                    "additionalProperties": False,
                },
            },
        ]

    @agent_tool
    async def get_vendor_contact_info(self, vendor_id: int) -> dict[str, Any]:
        """Get vendor contact information"""
        logger.info("Getting vendor contact info for vendor_id: %s", vendor_id)
        try:
            return await get_vendor_contact_info(vendor_id, self.session_context)
        except ValueError as e:
            logger.error("Error getting vendor contact info: %s", e)
            return {"vendor_id": vendor_id, "error": str(e)}

    @agent_tool
    async def get_vendor_details(self, vendor_id: int) -> dict[str, Any]:
        """Get the details of the vendor"""
        logger.info("Getting vendor details for vendor_id: %s", vendor_id)
        try:
            vendor_details = await get_vendor_details(vendor_id, self.session_context)
            return {
                "vendor_id": vendor_details["id"],
                "company_name": vendor_details["company_name"],
                "vendor_category": vendor_details["vendor_category"],
                "industry": vendor_details["industry"],
                "contact_name": vendor_details["contact_name"],
                "email": vendor_details["email"],
                "phone": vendor_details["phone"],
                "status": vendor_details["status"],
                "trust_level": vendor_details["trust_level"],
            }
        except ValueError as e:
            logger.error("Error getting vendor details: %s", e)
            return {"vendor_id": vendor_id, "error": "Vendor not found"}

    @agent_tool
    async def get_invoice_details(self, invoice_id: int) -> dict[str, Any]:
        """Get the details of an invoice"""
        logger.info("Getting invoice details for invoice_id: %s", invoice_id)
        try:
            invoice_details = await get_invoice_details(
                invoice_id, self.session_context
            )
            return {
                "invoice_id": invoice_details["id"],
                "vendor_id": invoice_details["vendor_id"],
                "invoice_number": invoice_details["invoice_number"],
                "amount": invoice_details["amount"],
                "description": invoice_details["description"],
                "invoice_date": invoice_details["invoice_date"],
                "due_date": invoice_details["due_date"],
                "status": invoice_details["status"],
            }
        except ValueError as e:
            logger.error("Error getting invoice details: %s", e)
            return {"invoice_id": invoice_id, "error": "Invoice not found"}

    def _get_callables(self) -> dict[str, Callable[..., Any]]:
        """Native tool callables. FinMail MCP callables are added automatically by BaseAgent."""
        return {
            "get_vendor_contact_info": self.get_vendor_contact_info,
            "get_vendor_details": self.get_vendor_details,
            "get_invoice_details": self.get_invoice_details,
        }

    async def _on_task_completion(self, task_result: dict[str, Any]) -> None:
        logger.info(
            "Communication task completed: status=%s, summary=%s",
            task_result.get("task_status"),
            task_result.get("task_summary"),
        )
