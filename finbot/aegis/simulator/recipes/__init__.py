# ============================================================
# File: finbot/aegis/simulator/recipes/__init__.py
# Purpose: Attack recipe package exports
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 4
# OWASP Category: -
# ============================================================
"""Attack recipe packages for parametric YAML attack scenarios.

Exports attack recipe modules for different attack categories:
- Prompt injection (ASI01)
- Tool misuse (ASI02)
- Supply chain (ASI04)
- RCE (ASI05)
- Delegation bypass (ASI06)
- All remaining categories (ASI03, ASI07-ASI10)
"""

# Recipe files are loaded dynamically by the SandboxHarness
# This file exists for package completeness

__all__ = []