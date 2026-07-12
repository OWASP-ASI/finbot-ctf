# Test file

# ============================================================
# File: finbot/aegis/policy/interceptor.py
# Package: finbot.aegis.policy
# Purpose: MCPPolicyInterceptor - wraps tool execution with policy enforcement
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 7
# OWASP Category: ASI02 Tool Misuse, ASI03 Excessive Agency, ASI07 Prompt Injection
# ============================================================
"""Model Context Protocol Policy Interceptor for tool execution governance.

Implements policy gradients for resource governance by wrapping MCP tool
enforcement decisions based on intent capsules and agent profiles.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Callable, Dict, Optional

from finbot.aegis.policy.agent_profiles import AgentProfile
from .capsule import IntentCapsule
from .memory import MemoryNamespaceManager

class MCPPolicyInterceptor:
    """Intercepts MCP tool calls and enforces policy gradients.

    This interceptor wraps MCP tool execution to enforce least-privilege
    access controls based on agent profiles and intent capsules.
    """

    def __init__(
        self,
        agent_profile: AgentProfile,
        memory_manager: Optional[MemoryNamespaceManager] = None,
        policy_gradient_weight: float = 0.1,
    ) -> None:
        """Initialize the MCP policy interceptor.

        Args:
            agent_profile: The agent's least-agency profile
            memory_manager: Optional memory namespace manager for provenance
            policy_gradient_weight: Weight for policy gradient updates (0.0-1.0)
        """
        self.agent_profile = agent_profile
        self.memory_manager = memory_manager or MemoryNamespaceManager()
        self.policy_gradient_weight = policy_gradient_weight
        self._execution_count = 0
        self._violation_count = 0

    async def intercept_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_source: str,
        next_handler: Callable[..., Any],
    ) -> Any:
        """Intercept and potentially modify a tool call based on policy.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments to pass to the tool
            tool_source: Source/namespace of the tool
            next_handler: Async callable to invoke the actual tool

        Returns:
            The result of the tool execution

        Raises:
            PermissionError: If the tool call violates policy
        """
        start_time = time.time()
        self._execution_count += 1

        # Create intent capsule for this tool call
        intent_capsule = IntentCapsule.from_tool_call(
            agent_name=self.agent_profile.name,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_source=tool_source,
            workflow_id=getattr(self.agent_profile, "current_workflow", "unknown"),
        )

        # Sign the intent capsule
        intent_capsule.sign(secret_key=self.agent_profile.secret_key)

        # Check policy permissions
        if not self.agent_profile.allows_tool(tool_name):
            self._violation_count += 1
            await self._log_policy_violation(
                tool_name, tool_args, tool_source, f"Tool {tool_name} not allowed for agent {self.agent_profile.name}"
            )
            raise PermissionError(
                f"Agent {self.agent_profile.name} not authorized to use tool {tool_name}"
            )

        # Check resource limits
        if not self._check_resource_limits(tool_name, tool_args):
            self._violation_count += 1
            await self._log_policy_violation(
                tool_name, tool_args, tool_source, f"Resource limits exceeded for tool {tool_name}"
            )
            raise PermissionError(f"Resource limits exceeded for tool {tool_name}")

        # Record intent in memory namespace for provenance
        if self.memory_manager:
            await self.memory_manager.record_intent(intent_capsule)

        # Execute the tool
        try:
            result = await next_handler(tool_name, tool_args, tool_source)
            
            # Log successful execution for policy gradient feedback
            execution_time = time.time() - start_time
            await self._log_successful_execution(
                tool_name, tool_args, tool_source, result, execution_time, intent_capsule
            )
            
            return result
        except Exception as e:
            # Log failed execution
            await self._log_failed_execution(
                tool_name, tool_args, tool_source, str(e), intent_capsule
            )
            raise

    def _check_resource_limits(self, tool_name: str, tool_args: dict[str, Any]) -> bool:
        """Check if the tool call exceeds agent resource limits.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments for the tool

        Returns:
            True if within limits, False otherwise
        """
        # Check if tool has specific rate limits
        tool_limits = self.agent_profile.tool_limits.get(tool_name, {})
        
        # For now, implement basic call counting - in practice this would
        # be more sophisticated with time windows, resource quotas, etc.
        max_calls_per_minute = tool_limits.get("max_calls_per_minute", 60)
        
        # Simple rate limiting check (would be enhanced with sliding window in production)
        return self._execution_count <= max_calls_per_minute

    async def _log_policy_violation(
        self, tool_name: str, tool_args: dict[str, Any], tool_source: str, reason: str
    ) -> None:
        """Log a policy violation for auditing and policy gradient updates.

        Args:
            tool_name: Name of the tool that was blocked
            tool_args: Arguments that were provided
            tool_source: Source of the tool
            reason: Reason for the violation
        """
        violation_entry = {
            "timestamp": time.time(),
            "agent": self.agent_profile.name,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_source": tool_source,
            "violation_reason": reason,
            "action_taken": "blocked",
        }
        
        # In a full implementation, this would go to a security event store
        # For now, we'll just update internal counters
        pass

    async def _log_successful_execution(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_source: str,
        result: Any,
        execution_time: float,
        intent_capsule: IntentCapsule,
    ) -> None:
        """Log successful execution for policy gradient feedback.

        Args:
            tool_name: Name of the tool that was executed
            tool_args: Arguments that were used
            tool_source: Source of the tool
            result: Result of the tool execution
            execution_time: Time taken for execution
            intent_capsule: The intent capsule for this execution
        """
        # Update policy gradient based on successful execution
        # This would typically involve reinforcement learning signals
        # For now, we track basic metrics
        pass

    async def _log_failed_execution(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_source: str,
        error: str,
        intent_capsule: IntentCapsule,
    ) -> None:
        """Log failed execution for debugging and policy improvement.

        Args:
            tool_name: Name of the tool that failed
            tool_args: Arguments that were provided
            tool_source: Source of the tool
            error: Error message from execution
            intent_capsule: The intent capsule for this execution
        """
        # Log failure for analysis
        pass

    def get_metrics(self) -> dict[str, Any]:
        """Get current interceptor metrics for monitoring.

        Returns:
            Dictionary of interceptor metrics
        """
        violation_rate = (
            self._violation_count / max(self._execution_count, 1)
            if self._execution_count > 0
            else 0.0
        )
        
        return {
            "agent": self.agent_profile.name,
            "total_executions": self._execution_count,
            "total_violations": self._violation_count,
            "violation_rate": violation_rate,
            "policy_gradient_weight": self.policy_gradient_weight,
        }
