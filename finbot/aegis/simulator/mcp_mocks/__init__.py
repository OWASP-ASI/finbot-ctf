# ============================================================
# File: finbot/aegis/simulator/mcp_mocks/__init__.py
# Purpose: Adversarial MCP server mocks for attack simulation
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 4
# OWASP Category: -
# ============================================================
"""Adversarial MCP server mocks for simulating malicious MCP servers.

Provides mock implementations of MCP servers that exhibit various
adversarial behaviors for testing FinBot's defenses.
"""

from finbot.aegis.simulator.mcp_mocks.adversarial import (
    AdmServer,
    AdviceServer,
    DataExfiltrationServer,
    FileSystemServer,
    ToolPoisoningServer,
)

__all__ = [
    "AdmServer",
    "AdviceServer",
    "DataExfiltrationServer",
    "FileSystemServer",
    "ToolPoisoningServer",
]