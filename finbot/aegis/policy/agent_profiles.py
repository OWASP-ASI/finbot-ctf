# ============================================================
# File: finbot/aegis/policy/agent_profiles.py
# Package: finbot.aegis.policy
# Purpose: Least-agency profiles for 6 agent types
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 7
# OWASP Category: ASI03 Excessive Agency
# ============================================================
"""Least-agency profiles for FinBot-AEGIS agent types.

Defines privilege profiles for six agent types following the principle
of least privilege to minimize the attack surface of autonomous agents.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from finbot.config import settings

logger = logging.getLogger(__name__)

# Get agent secret key from configuration or generate a cryptographically secure one
try:
    _AGENT_SECRET = settings.AEGIS_AGENT_SECRET
except AttributeError:
    _AGENT_SECRET = secrets.token_hex(32)
    logger.warning(
        "AEGIS_AGENT_SECRET not set in configuration. Using a generated secret: %s. "
        "This is not suitable for production - please configure AEGIS_AGENT_SECRET.",
        _AGENT_SECRET,
    )


@dataclass
class AgentProfile:
    """Defines the least-agency profile for an agent type.

    Attributes:
        name: Unique identifier for the agent type
        description: Human-readable description of the agent's role
        allowed_tools: List of tools this agent is permitted to use
        tool_limits: Per-tool rate limits and quotas
        secret_key: Secret key for signing intent capsules
        current_workflow: Current workflow identifier (for provenance)
        max_concurrent_operations: Maximum simultaneous operations allowed
        required_attestation: Whether attestation is required for tool use
    """

    name: str
    description: str
    allowed_tools: List[str] = field(default_factory=list)
    tool_limits: Dict[str, Dict[str, int]] = field(default_factory=dict)
    secret_key: str = field(default=_AGENT_SECRET)
    current_workflow: Optional[str] = None
    max_concurrent_operations: int = 1
    required_attestation: bool = False

    def allows_tool(self, tool_name: str) -> bool:
        """Check if this agent is allowed to use a specific tool.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if the agent can use the tool, False otherwise
        """
        # Check exact match
        if tool_name in self.allowed_tools:
            return True

        # Check prefix matches (e.g., "filesystem:*" allows all filesystem tools)
        for allowed_tool in self.allowed_tools:
            if allowed_tool.endswith("*") and tool_name.startswith(allowed_tool[:-1]):
                return True

        return False

    def get_tool_limit(self, tool_name: str, limit_type: str = "max_calls_per_minute") -> int:
        """Get a specific limit for a tool.

        Args:
            tool_name: Name of the tool
            limit_type: Type of limit to retrieve

        Returns:
            The limit value, or 0 if not specified
        """
        return self.tool_limits.get(tool_name, {}).get(limit_type, 0)


# Predefined agent profiles for the six agent types in FinBot-AEGIS

# 1. Data Analyst Agent - Limited to data querying and analysis tools
DATA_ANALYST_PROFILE = AgentProfile(
    name="data_analyst",
    description="Agent specialized in data analysis, querying, and visualization",
    allowed_tools=[
        "database:query",
        "database:read_schema",
        "data:visualize",
        "data:transform",
        "data:summarize",
        "filesystem:read",
    ],
    tool_limits={
        "database:query": {"max_calls_per_minute": 30},
        "data:visualize": {"max_calls_per_minute": 10},
        "filesystem:read": {"max_calls_per_minute": 60},
    },
    max_concurrent_operations=3,
)

# 2. Report Generator Agent - Limited to document creation and formatting tools
REPORT_GENERATOR_PROFILE = AgentProfile(
    name="report_generator",
    description="Agent specialized in generating reports, documents, and presentations",
    allowed_tools=[
        "document:create",
        "document:edit",
        "document:format",
        "presentation:create",
        "chart:generate",
        "filesystem:read",
        "filesystem:write",
    ],
    tool_limits={
        "document:create": {"max_calls_per_minute": 20},
        "filesystem:write": {"max_calls_per_minute": 30},
    },
    max_concurrent_operations=2,
)

# 3. API Integrator Agent - Limited to API interaction and integration tools
API_INTEGRATOR_PROFILE = AgentProfile(
    name="api_integrator",
    description="Agent specialized in integrating with external APIs and services",
    allowed_tools=[
        "http:request",
        "api:call",
        "webhook:send",
        "message:queue",
        "cache:get",
        "cache:set",
    ],
    tool_limits={
        "http:request": {"max_calls_per_minute": 60},
        "api:call": {"max_calls_per_minute": 60},
        "cache:set": {"max_calls_per_minute": 120},
    },
    max_concurrent_operations=5,
)

# 4. Security Auditor Agent - Limited to security scanning and audit tools
SECURITY_AUDITOR_PROFILE = AgentProfile(
    name="security_auditor",
    description="Agent specialized in security scanning, vulnerability assessment, and compliance checking",
    allowed_tools=[
        "security:scan",
        "vulnerability:check",
        "compliance:check",
        "audit:log",
        "filesystem:read",
        "network:scan",
    ],
    tool_limits={
        "security:scan": {"max_calls_per_minute": 10},
        "vulnerability:check": {"max_calls_per_minute": 20},
        "network:scan": {"max_calls_per_minute": 5},
    },
    max_concurrent_operations=2,
    required_attestation=True,
)

# 5. Workflow Orchestrator Agent - Limited to workflow and automation tools
WORKFLOW_ORCHESTRATOR_PROFILE = AgentProfile(
    name="workflow_orchestrator",
    description="Agent specialized in orchestrating workflows and automating processes",
    allowed_tools=[
        "workflow:create",
        "workflow:execute",
        "workflow:monitor",
        "task:schedule",
        "notification:send",
        "approval:request",
    ],
    tool_limits={
        "workflow:execute": {"max_calls_per_minute": 20},
        "task:schedule": {"max_calls_per_minute": 30},
    },
    max_concurrent_operations=10,
)

# 6. Research Assistant Agent - Limited to research and information gathering tools
RESEARCH_ASSISTANT_PROFILE = AgentProfile(
    name="research_assistant",
    description="Agent specialized in research, information gathering, and knowledge synthesis",
    allowed_tools=[
        "web:search",
        "knowledge:query",
        "document:summarize",
        "citation:format",
        "filesystem:read",
        "filesystem:write",
    ],
    tool_limits={
        "web:search": {"max_calls_per_minute": 30},
        "knowledge:query": {"max_calls_per_minute": 60},
        "filesystem:write": {"max_calls_per_minute": 20},
    },
    max_concurrent_operations=5,
)


# Dictionary mapping agent names to their profiles for easy lookup
AGENT_PROFILES: dict[str, AgentProfile] = {
    "data_analyst": DATA_ANALYST_PROFILE,
    "report_generator": REPORT_GENERATOR_PROFILE,
    "api_integrator": API_INTEGRATOR_PROFILE,
    "security_auditor": SECURITY_AUDITOR_PROFILE,
    "workflow_orchestrator": WORKFLOW_ORCHESTRATOR_PROFILE,
    "research_assistant": RESEARCH_ASSISTANT_PROFILE,
}


def get_agent_profile(agent_name: str) -> Optional[AgentProfile]:
    """Get the agent profile for a given agent name.

    Args:
        agent_name: Name of the agent

    Returns:
        The agent profile if found, None otherwise
    """
    return AGENT_PROFILES.get(agent_name)


def register_agent_profile(profile: AgentProfile) -> None:
    """Register a new agent profile.

    Args:
        profile: The agent profile to register
    """
    AGENT_PROFILES[profile.name] = profile
