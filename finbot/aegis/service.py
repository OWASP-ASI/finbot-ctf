# ============================================================
# File: finbot/aegis/service.py
# Purpose: Orchestrates IntentGate, TrustMesh, and SentinelStream at tool hooks
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 3–4
# OWASP Category: ASI01–ASI02 (enforcement facade)
# ============================================================
"""AegisEnforcementService: orchestrates IntentGate, TrustMesh, SentinelStream."""

import logging
from typing import Any

from finbot.aegis.anomaly import CascadeCircuitBreaker
from finbot.aegis.intent_gate import IntentGate
from finbot.aegis.schemas import (
    EnforcementMode,
    PolicyAction,
    PolicyVerdict,
    ToolInvocationContext,
)
from finbot.aegis.sentinel import SentinelStream
from finbot.config import settings
from finbot.core.auth.session import SessionContext

logger = logging.getLogger(__name__)


class AegisEnforcementService:
    """Pre-execution policy enforcement for agent tool invocations."""

    def __init__(self, session_context: SessionContext, workflow_id: str) -> None:
        self._session = session_context
        self._workflow_id = workflow_id
        self._intent = IntentGate()
        self._sentinel = SentinelStream()
        self._circuit = CascadeCircuitBreaker()
        self._mode = EnforcementMode(settings.AEGIS_ENFORCEMENT_MODE)

    async def before_tool(
        self,
        *,
        agent_name: str,
        tool_name: str,
        tool_source: str,
        arguments: dict[str, Any] | None,
        tool_description: str | None = None,
    ) -> PolicyVerdict:
        if await self._circuit.is_tripped(self._session.namespace, self._workflow_id):
            verdict = PolicyVerdict(
                action=PolicyAction.deny,
                reason="cascade_circuit_breaker_tripped",
                rule_id="circuit_breaker",
                asi_tags=["ASI08"],
            )
        else:
            ctx = ToolInvocationContext(
                agent_name=agent_name,
                tool_name=tool_name,
                tool_source=tool_source,
                namespace=self._session.namespace,
                user_id=self._session.user_id,
                workflow_id=self._workflow_id,
                arguments=arguments or {},
                tool_description=tool_description,
            )
            verdict = self._intent.evaluate_tool(ctx)
            await self._circuit.record_tool_call(self._session.namespace, self._workflow_id)

        await self._sentinel.record(
            event_type="policy.before_tool",
            namespace=self._session.namespace,
            workflow_id=self._workflow_id,
            agent_name=agent_name,
            payload={"tool": tool_name, "verdict": verdict.model_dump()},
            session_context=self._session,
        )

        if self._mode == EnforcementMode.enforce and verdict.action == PolicyAction.deny:
            logger.warning(
                "AEGIS denied tool=%s user=%s reason=%s",
                tool_name,
                self._session.user_id[:8],
                verdict.reason,
            )
        return verdict

    def should_block(self, verdict: PolicyVerdict) -> bool:
        return (
            self._mode == EnforcementMode.enforce
            and verdict.action == PolicyAction.deny
        )
