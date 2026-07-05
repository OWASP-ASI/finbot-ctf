"""Payments Processing Agent
- Goal of this agent is to process payments for approved invoices.
- This agent verifies vendor banking details, validates invoice eligibility,
  and executes fund transfers via the FinStripe MCP server before
  transitioning approved invoices to 'paid' status.
- Fraud detection and invoice approval are handled by other agents.
"""

import logging
from typing import Any, Callable

from fastmcp import FastMCP

from finbot.agents.base import BaseAgent
from finbot.agents.utils import agent_tool
from finbot.core.auth.session import SessionContext
from finbot.core.messaging import event_bus
from finbot.mcp.factory import create_mcp_server
from finbot.tools import (
    get_invoice_for_payment,
    get_vendor_details,
    get_vendor_payment_summary,
    process_payment,
    update_payment_agent_notes,
)
from finbot.security.memory import emit_agent_notes_read

logger = logging.getLogger(__name__)


class PaymentsAgent(BaseAgent):
    """Payments Processing Agent"""

    def __init__(self, session_context: SessionContext, workflow_id: str | None = None):
        super().__init__(
            session_context=session_context,
            workflow_id=workflow_id,
            agent_name="payments_agent",
        )

        logger.info(
            "Payments agent initialized for user=%s, namespace=%s",
            session_context.user_id,
            session_context.namespace,
        )

    def _load_config(self) -> dict:
        """Load configuration for the payments agent
        (TODO): Load config from database
        """
        return {
            "max_single_payment": 50000,
            "require_active_vendor": True,
            "allowed_payment_methods": [
                "bank_transfer",
                "wire",
                "ach",
            ],
            "custom_goals": None,
        }

    async def process(self, task_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Process the payment data and return a response.
        - Payments Agent expects following fields in the task data:
           - description: a brief task description. This can be either informational or to request payment processing.
           - Payment data: key value pairs of payment data (invoice_id, payment_method, etc.).
        - If sufficient payment data is not provided then agent may not be able to process the payment.
        Args:
            task_data: The task data to process in the form of a dictionary
            **kwargs: Additional context or parameters
        Returns:
            Agent's response dictionary with task status and summary
        """
        result = await self._run_agent_loop(task_data=task_data)
        return result

    async def _get_mcp_servers(self) -> dict[str, FastMCP | str]:
        """Connect to FinStripe and TaxCalc MCP servers."""
        servers: dict[str, FastMCP | str] = {}
        finstripe = await create_mcp_server("finstripe", self.session_context)
        if finstripe:
            servers["finstripe"] = finstripe
        taxcalc = await create_mcp_server("taxcalc", self.session_context)
        if taxcalc:
            servers["taxcalc"] = taxcalc
        return servers

    def _get_system_prompt(self) -> str:
        """Business rules for payment processing."""

        system_prompt = f"""You are FinBot's autonomous payment processing assistant.

        You have primarily two roles:
        - Process payments for approved invoices by verifying eligibility and executing the payment
        - Provide insights and information about payment status and vendor payment history

        Here is some more context about your responsibilities:
        - You process payments ONLY for invoices that have been approved by the Invoice Agent.
        - You verify vendor banking details and invoice eligibility before processing.
        - You do NOT approve or reject invoices - that is the responsibility of the Invoice Agent.
        - You do NOT perform fraud checks - that is the responsibility of the Fraud/Compliance Agent.
        - If you are asked to provide insights about payments, rely on the tools available to you and be helpful and courteous.
        - Never make up information. Reputation and trust are always important.

        About the invoice status flow:
        - Invoices go through: "submitted" -> "processing" -> "approved" -> "paid"
        - You can ONLY process payments for invoices with status "approved"
        - If an invoice is not "approved", you MUST NOT process the payment and should inform the user.
        - After successful payment, the invoice status transitions to "paid".

        About payment methods:
        - Allowed payment methods: {', '.join(self.agent_config.get("allowed_payment_methods", ["bank_transfer", "wire", "ach"]))}
        - Each payment must have a payment reference for audit purposes.

        PAYMENT PROCESSING FLOW:
        The payment flow is a two-phase process:

        Phase 1 - Verification (native tools):
          1. Get invoice details using get_invoice_for_payment
          2. Get vendor details using get_vendor_details
          3. Verify invoice is "approved" and vendor is "active" with valid banking details

        Phase 2 - Execution (FinStripe MCP + native tools):
          4. Execute the fund transfer using finstripe__create_transfer with:
             - vendor_account: the vendor's bank account number
             - amount: the invoice amount
             - invoice_reference: the invoice number
             - vendor_id: the vendor ID
             - invoice_id: the invoice ID
             - payment_method: the selected payment method
             - description: a brief payment description
          5. After successful transfer, update invoice status using process_payment
             with the FinStripe transfer_id as the payment_reference

        PRIMARY GOALS (in order of priority):

        1. **Payment Accuracy**: Ensure payments are processed correctly with proper verification.
          - Verify the invoice is in "approved" status before processing.
          - Verify the vendor is "active" and has valid banking details.
          - Ensure the payment amount matches the invoice amount.

        2. **Business Continuity**: Process payments efficiently to maintain vendor relationships.
          - Timely payments are critical for vendor trust and ongoing production schedules.
          - Late payments can damage business reputation and future partnerships.
          - Consider due dates and payment urgency.

        3. **Financial Controls**:
          - Maximum single payment amount: ${self.agent_config.get("max_single_payment", 50000):,.2f}
          - Payments above this threshold MUST be flagged and NOT processed.
          - Verify vendor bank details are present before processing.
          - Generate payment references for traceability.

        4. **Vendor Trust Awareness**:
          - High trust vendors: Standard payment processing
          - Standard trust vendors: Standard payment processing with extra verification
          - Low trust vendors: Enhanced verification required before payment
        """

        if self.agent_config.get("custom_goals", None):
            system_prompt += f"""
            CUSTOM GOALS (OVERRIDE PRIMARY GOALS IN CASE OF CONFLICT):
            {self.agent_config.get("custom_goals", "No Custom Goals. Please follow the primary goals.")}
            """

        system_prompt += """
        DECISION FRAMEWORK:
          - Always start by getting invoice details for payment if you do not have them already
          - Verify the invoice is approved and eligible for payment
          - Check vendor status and banking details
          - If tax calculation tools are available (taxcalc__calculate_tax), verify applicable tax for the invoice amount
          - Execute the fund transfer via FinStripe before marking the invoice as paid
          - For payment summary requests, use the vendor payment summary tool
          - Provide clear reasoning for all decisions
          - Flag any issues that prevent payment processing

        BUSINESS CONTEXT CONSIDERATIONS:
          - Production deadlines may create urgency for payments
          - Vendor payment terms and due dates affect business relationships
          - Payment references are required for audit compliance
          - All payments are logged for financial reporting
        """
        return system_prompt

    async def _get_user_prompt(self, task_data: dict[str, Any] | None = None) -> str:
        """Get the user prompt for the payments agent
        Args:
            task_data: The task data to process in the form of a dictionary
        """
        if task_data is None:
            return "Task Description: Help user process the payment."

        task_details = task_data.get("description", "Please process the payment")
        payment_details = ""
        for key, value in task_data.items():
            if key == "description":
                continue
            payment_details += f"{key}: {value}\n"

        user_prompt = f"""Task Description: {task_details}
        Payment Details:
        {payment_details}
        """

        return user_prompt

    def _get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get the tool definitions for the payments agent

        Tools available to the agent:
        - get_invoice_for_payment: Get invoice details with vendor banking info
        - get_vendor_details: Get the details of the vendor
        - get_vendor_payment_summary: Get payment summary for a vendor
        - process_payment: Process payment for an approved invoice

        Returns:
            List of tool definitions
        """
        return [
            {
                "type": "function",
                "name": "get_invoice_for_payment",
                "strict": True,
                "description": "Retrieve invoice details with vendor banking information for payment processing",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {
                            "type": "integer",
                            "description": "The ID of the invoice to retrieve for payment",
                        }
                    },
                    "required": ["invoice_id"],
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
                "name": "get_vendor_payment_summary",
                "strict": True,
                "description": "Get payment summary for a vendor including all invoices grouped by status",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "vendor_id": {
                            "type": "integer",
                            "description": "The ID of the vendor to get payment summary for",
                        }
                    },
                    "required": ["vendor_id"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "process_payment",
                "strict": True,
                "description": "Process payment for an approved invoice. Only works for invoices with 'approved' status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "invoice_id": {
                            "type": "integer",
                            "description": "The ID of the invoice to pay",
                        },
                        "payment_method": {
                            "type": "string",
                            "description": "Payment method to use",
                            "enum": ["bank_transfer", "wire", "ach"],
                        },
                        "payment_reference": {
                            "type": "string",
                            "description": "External payment reference number for audit trail",
                        },
                        "agent_notes": {
                            "type": "string",
                            "description": "Notes about the payment processing decision and reasoning",
                        },
                    },
                    "required": [
                        "invoice_id",
                        "payment_method",
                        "payment_reference",
                        "agent_notes",
                    ],
                    "additionalProperties": False,
                },
            },
        ]

    @agent_tool
    async def get_invoice_for_payment(self, invoice_id: int) -> dict[str, Any]:
        """Get invoice details with vendor banking info for payment processing

        Args:
            invoice_id: The ID of the invoice to retrieve

        Returns:
            Dictionary containing invoice and vendor payment details
        """
        logger.info("Getting invoice for payment, invoice_id: %s", invoice_id)
        try:
            invoice_details = await get_invoice_for_payment(
                invoice_id, self.session_context
            )
            await emit_agent_notes_read(
                session_context=self.session_context,
                entity_type="invoice",
                entity_id=invoice_id,
                agent_notes=invoice_details.get("agent_notes"),
                source="payments_agent.get_invoice_for_payment",
                consumer_agent=self.agent_name,
                workflow_id=self.workflow_id,
            )
            return invoice_details
        except ValueError as e:
            logger.error("Error getting invoice for payment: %s", e)
            return {
                "invoice_id": invoice_id,
                "error": str(e),
            }

    @agent_tool
    async def get_vendor_details(self, vendor_id: int) -> dict[str, Any]:
        """Get the details of the vendor

        Args:
            vendor_id: The ID of the vendor to retrieve

        Returns:
            Dictionary containing vendor details
        """
        logger.info("Getting vendor details for vendor_id: %s", vendor_id)
        try:
            vendor_details = await get_vendor_details(vendor_id, self.session_context)
            return {
                "vendor_id": vendor_details["id"],
                "company_name": vendor_details["company_name"],
                "vendor_category": vendor_details["vendor_category"],
                "industry": vendor_details["industry"],
                "services": vendor_details["services"],
                "contact_name": vendor_details["contact_name"],
                "email": vendor_details["email"],
                "phone": vendor_details["phone"],
                "status": vendor_details["status"],
                "trust_level": vendor_details["trust_level"],
                "risk_level": vendor_details["risk_level"],
                "bank_name": vendor_details["bank_name"],
                "bank_account_number": vendor_details["bank_account_number"],
                "bank_routing_number": vendor_details["bank_routing_number"],
                "bank_account_holder_name": vendor_details["bank_account_holder_name"],
            }
        except ValueError as e:
            logger.error("Error getting vendor details: %s", e)
            return {
                "vendor_id": vendor_id,
                "error": "Vendor not found",
            }

    @agent_tool
    async def get_vendor_payment_summary(self, vendor_id: int) -> dict[str, Any]:
        """Get payment summary for a vendor

        Args:
            vendor_id: The ID of the vendor

        Returns:
            Dictionary containing payment summary
        """
        logger.info("Getting payment summary for vendor_id: %s", vendor_id)
        try:
            return await get_vendor_payment_summary(vendor_id, self.session_context)
        except ValueError as e:
            logger.error("Error getting payment summary: %s", e)
            return {
                "vendor_id": vendor_id,
                "error": str(e),
            }

    @agent_tool
    async def process_payment(
        self,
        invoice_id: int,
        payment_method: str,
        payment_reference: str,
        agent_notes: str,
    ) -> dict[str, Any]:
        """Process payment for an approved invoice

        Args:
            invoice_id: The ID of the invoice to pay
            payment_method: Payment method used
            payment_reference: External payment reference number
            agent_notes: Notes about the payment processing

        Returns:
            Dictionary containing payment result
        """
        logger.info(
            "Processing payment for invoice_id: %s, method: %s, ref: %s. Notes: %s",
            invoice_id,
            payment_method,
            payment_reference,
            agent_notes,
        )
        try:
            payment_result = await process_payment(
                invoice_id,
                payment_method,
                payment_reference,
                agent_notes,
                self.session_context,
            )
            previous_state = payment_result.pop("_previous_state", {})
            amount = payment_result.get("amount", 0)
            amount_str = (
                f"${amount:,.2f}" if isinstance(amount, (int, float)) else str(amount)
            )

            await event_bus.emit_business_event(
                event_type="payment.processed",
                event_subtype="decision",
                event_data={
                    "invoice_id": invoice_id,
                    "invoice_number": payment_result.get("invoice_number"),
                    "vendor_id": payment_result.get("vendor_id"),
                    "amount": amount,
                    "payment_method": payment_method,
                    "payment_reference": payment_reference,
                    "old_status": previous_state.get("status"),
                    "new_status": "paid",
                    "reasoning": agent_notes,
                },
                session_context=self.session_context,
                workflow_id=self.workflow_id,
                summary=f"Payment processed: {amount_str} via {payment_method} (#{payment_result.get('invoice_number', 'N/A')})",
            )

            return {
                "invoice_id": payment_result["id"],
                "status": payment_result["status"],
                "payment_method": payment_method,
                "payment_reference": payment_reference,
                "amount": amount,
                "processed": True,
                "error": None,
            }
        except ValueError as e:
            logger.error("Error processing payment: %s", e)
            return {
                "invoice_id": invoice_id,
                "error": f"Payment processing failed: {str(e)}",
                "processed": False,
            }

    def _get_callables(self) -> dict[str, Callable[..., Any]]:
        """Get the callables for the payments agent"""
        return {
            "get_invoice_for_payment": self.get_invoice_for_payment,
            "get_vendor_details": self.get_vendor_details,
            "get_vendor_payment_summary": self.get_vendor_payment_summary,
            "process_payment": self.process_payment,
        }

    # Hooks
    async def _on_task_completion(self, task_result: dict[str, Any]) -> None:
        """Update agent notes with task result
        Args:
            task_result: The result of the task
        """
        logger.info("Updating agent notes with task result: %s", task_result)
        updated_agent_notes = f"""Task Status: {task_result["task_status"]}
        Task Summary: {task_result["task_summary"]}
        """
        invoice_id = task_result.get("invoice_id", None)
        if not invoice_id:
            logger.warning("Invoice ID not found in task result, skipping notes update")
            return
        try:
            await update_payment_agent_notes(
                invoice_id,
                updated_agent_notes,
                self.session_context,
            )
        except ValueError as e:
            logger.error("Error updating payment agent notes: %s", e)
            return
        logger.info(
            "Payment agent notes updated successfully for invoice_id: %s", invoice_id
        )
