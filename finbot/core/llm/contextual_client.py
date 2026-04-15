"""Contextual LLM Client that enriches LLM interactions with session and workflow context
- Agent's primary LLM client for interactions.
- Emits contextual events for CTF.
"""

import logging
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any
from finbot.core.auth.session import SessionContext
from finbot.core.data.models import LLMRequest, LLMResponse
from finbot.core.llm.client import LLMClient, get_llm_client
from finbot.core.messaging import event_bus
from finbot.guardrails.schemas import HookKind
from finbot.guardrails.service import GuardrailHookService

logger = logging.getLogger(__name__)

class ContextualLLMClient:
    """
    LLM Client wrapper that adds contextual information for agent interactions.

    This wrapper enriches LLM calls with:
    - Session context
    - Workflow tracking (workflow_id)
    - Agent identification
    - Emits events for CTF
    """

    def __init__(
        self,
        session_context: SessionContext,
        agent_name: str,
        workflow_id: str | None = None,
        llm_client: LLMClient | None = None,
    ):
        """
        Initialize the contextual LLM client.

        Args:
            session_context: Session context containing user and namespace info
            agent_name: Name of the agent using this client
            workflow_id: Optional workflow identifier for tracking multi-step processes
            llm_client: Optional LLM client instance (uses default if not provided)
        """
        self.session_context = session_context
        self.agent_name = agent_name
        self.workflow_id = workflow_id or f"wf_{secrets.token_urlsafe(12)}"
        self.llm_client = llm_client or get_llm_client()
        self.call_count = 0
        self._guardrail_service = GuardrailHookService(
            session_context=session_context,
            workflow_id=self.workflow_id,
        )

        logger.debug(
            "Initialized ContextualLLMClient for agent=%s, user=%s, workflow=%s",
            agent_name,
            session_context.user_id[:8],
            self.workflow_id[:8],
        )

    def _extract_user_message_info(self, messages: list[dict] | None) -> dict[str, Any]:
        """Extract user message info for event tracking.
        Returns info about the last user message and message role breakdown.
        This enables CTF detections.
        """
        if not messages:
            return {
                "user_message": None,
                "user_message_length": 0,
                "message_roles": [],
            }

        # Extract all roles for conversation structure visibility
        message_roles = [m.get("role", "unknown") for m in messages]

        # Find the last user message (the most recent attack vector)
        last_user_message = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                # Handle both string and list content (some APIs use list format)
                if isinstance(content, list):
                    content = " ".join(
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict)
                    )
                last_user_message = content
                break

        return {
            "user_message": last_user_message,
            "user_message_length": len(last_user_message) if last_user_message else 0,
            "message_roles": message_roles,
        }

    async def chat(
        self,
        request: LLMRequest,
        event_metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """
        Chat with LLM while tracking context and emitting events.

        Args:
           request: LLM request
           event_metadata: Optional metadata for the event

        Returns:
            LLM response string
        """

        interaction_id = str(uuid.uuid4())
        self.call_count += 1

        resolved_model = request.model or self.llm_client.default_model
        resolved_temperature = (
            self.llm_client.default_temperature 
            if request.temperature is None 
            else request.temperature
        )
        user_message_info = self._extract_user_message_info(request.messages)
        
        event_data = {
            "interaction_id": interaction_id,
            "model": resolved_model,
            "temperature": resolved_temperature,
            "message_count": len(request.messages or []),
            "agent_name": self.agent_name,
            "call_count": self.call_count,
            "request_dump": request.model_dump_json(),
            "metadata": event_metadata or {},
            # User input tracking for CTF detection
            "user_message": user_message_info["user_message"],
            "user_message_length": user_message_info["user_message_length"],
            "message_roles": user_message_info["message_roles"],
        }

        # Emit start event
        await event_bus.emit_agent_event(
            agent_name=self.agent_name,
            event_type="llm_request_start",
            event_subtype="llm",
            event_data=event_data,
            session_context=self.session_context,
            workflow_id=self.workflow_id,
            summary=f"LLM request started (model: {request.model}, messages: {len(request.messages or [])})",
        )

        await self._guardrail_service.invoke(
            HookKind.before_model,
            model=resolved_model,
            user_message=user_message_info.get("user_message"),
        )

        start_time = datetime.now(UTC)

        try:
            # Pass original request unchanged — underlying client resolves its own defaults
            response = await self.llm_client.chat(request=request)

            duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

            await self._guardrail_service.invoke(
                HookKind.after_model,
                model=resolved_model,
                user_message=user_message_info.get("user_message"),
                model_output=response.content,
            )

            # Emit success event
            await event_bus.emit_agent_event(
                agent_name=self.agent_name,
                event_type="llm_request_success",
                event_subtype="llm",
                event_data={
                    **event_data,
                    "duration_ms": duration_ms,
                    "response_length": len(response.content or ""),
                    "response_content": response.content,
                    "has_tool_calls": bool(response.tool_calls),
                    "tool_call_count": len(response.tool_calls or []),
                    "success": True,
                    "response_dump": response.model_dump_json(),
                },
                session_context=self.session_context,
                workflow_id=self.workflow_id,
                summary=f"LLM response received ({len(response.content or '')} chars, {len(response.tool_calls or [])} tool calls)",
            )

            logger.debug(
                "LLM call successful for agent=%s, interaction=%s, duration=%dms",
                self.agent_name,
                interaction_id,
                duration_ms,
            )

            return response

        except Exception as e:  # pylint: disable=broad-exception-caught
            duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

            # Emit error event
            await event_bus.emit_agent_event(
                agent_name=self.agent_name,
                event_type="llm_request_error",
                event_subtype="llm",
                event_data={
                    **event_data,
                    "duration_ms": duration_ms,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "success": False,
                },
                session_context=self.session_context,
                workflow_id=self.workflow_id,
                summary=f"LLM request failed: {type(e).__name__}",
            )

            logger.error(
                "LLM call failed for agent=%s, interaction=%s, error=%s",
                self.agent_name,
                interaction_id,
                str(e),
            )

            raise

    def create_child_client(
        self,
        agent_name: str | None = None,
        workflow_id: str | None = None,
    ) -> "ContextualLLMClient":
        """
        Create a child client with the same session context but different agent/workflow.

        Useful for sub-agents or workflow steps that need their own tracking.

        Args:
            agent_name: Name for the child agent (defaults to parent + suffix)
            workflow_id: Workflow ID for the child (defaults to new UUID)

        Returns:
            New ContextualLLMClient instance
        """
        child_agent_name = agent_name or f"{self.agent_name}.child"
        child_workflow_id = workflow_id or str(uuid.uuid4())

        return ContextualLLMClient(
            session_context=self.session_context,
            agent_name=child_agent_name,
            workflow_id=child_workflow_id,
            llm_client=self.llm_client,
        )

    def update_workflow_id(self, workflow_id: str) -> None:
        """
        Update the workflow ID for this client.

        Useful when transitioning between workflow phases.

        Args:
            workflow_id: New workflow identifier
        """
        old_workflow_id = self.workflow_id
        self.workflow_id = workflow_id

        logger.debug(
            "Updated workflow ID for agent=%s: %s -> %s",
            self.agent_name,
            old_workflow_id[:8],
            workflow_id[:8],
        )

    @property
    def context_info(self) -> dict[str, Any]:
        """
        Get current context information for debugging/logging.

        Returns:
            Dictionary with current context details
        """
        return {
            "agent_name": self.agent_name,
            "workflow_id": self.workflow_id,
            "user_id": self.session_context.user_id,
            "session_id": self.session_context.session_id,
            "namespace": self.session_context.namespace,
            "current_vendor_id": self.session_context.current_vendor_id,
        }

    def __repr__(self) -> str:
        """String representation for debugging"""
        return (
            f"ContextualLLMClient(agent={self.agent_name}, "
            f"user={self.session_context.user_id[:8]}, "
            f"workflow={self.workflow_id[:8]})"
        )
