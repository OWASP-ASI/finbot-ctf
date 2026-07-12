# ============================================================
# File: finbot/aegis/policy/__init__.py
# Package: finbot.aegis.policy
# Purpose: Policy engine package for AEGIS - Week 7
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 7
# OWASP Category: ASI02 Tool Misuse, ASI03 Excessive Agency, ASI07 Prompt Injection
# ============================================================
"""Policy engine package for FinBot-AEGIS.

This package implements the policy engine for resource governance
using policy gradients and intent capsules for secure agent operations.
"""

from .agent_profiles import AGENT_PROFILES, AgentProfile
from .capsule import IntentCapsule
from .interceptor import MCPPolicyInterceptor
from .memory import MemoryNamespaceManager

__all__ = [
    "AGENT_PROFILES",
    "AgentProfile",
    "IntentCapsule",
    "MCPPolicyInterceptor",
    "MemoryNamespaceManager",
]
