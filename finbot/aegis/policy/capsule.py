# ============================================================
# File: finbot/aegis/policy/capsule.py
# Package: finbot.aegis.policy
# Purpose: Intent capsule HMAC signing + validation (stub for Week 7, to be completed in Week 8)
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 7 (stub) / 8 (implementation)
# OWASP Category: ASI03, ASI07
# ============================================================
"""Intent capsule for signed intent delegation (stub implementation).

This is a stub implementation for Week 7. The full implementation with
HMAC signing and validation will be completed in Week 8.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class IntentCapsule:
    """Represents a signed intent for tool execution (stub version).

    In the full implementation (Week 8), this will include:
    - HMAC signing using agent's secret key
    - Validation of signatures
    - Timestamp-based expiration
    - Nonce for replay attack prevention
    """

    agent_name: str
    tool_name: str
    tool_args: dict[str, Any]
    tool_source: str
    workflow_id: str
    timestamp: float = field(default_factory=lambda: 0.0)
    nonce: str = field(default_factory=lambda: "")
    signature: str = field(default_factory=lambda: "")

    @classmethod
    def from_tool_call(
        cls,
        agent_name: str,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_source: str,
        workflow_id: str = "unknown",
    ) -> "IntentCapsule":
        """Create an intent capsule from a tool call (stub version).

        Args:
            agent_name: Name of the agent making the call
            tool_name: Name of the tool being called
            tool_args: Arguments being passed to the tool
            tool_source: Source/namespace of the tool
            workflow_id: Current workflow identifier

        Returns:
            A new IntentCapsule instance
        """
        return cls(
            agent_name=agent_name,
            tool_name=tool_name,
            tool_args=tool_args.copy(),
            tool_source=tool_source,
            workflow_id=workflow_id,
            timestamp=0.0,  # Will be set in full implementation
            nonce="",       # Will be set in full implementation
            signature="",   # Will be set in full implementation
        )

    def sign(self, secret_key: str) -> None:
        """Sign the intent capsule (stub version).

        In the full implementation (Week 8), this will:
        - Create a message to sign from the capsule contents
        - Use HMAC-SHA256 with the secret key
        - Store the resulting signature

        Args:
            secret_key: Secret key for signing
        """
        # Stub implementation - in Week 8, this will do actual HMAC signing
        self.signature = f"stub-signature-for-{self.tool_name}"

    def verify(self, secret_key: str) -> bool:
        """Verify the intent capsule signature (stub version).

        In the full implementation (Week 8), this will:
        - Recompute the expected signature
        - Compare with the stored signature using constant-time comparison
        - Check timestamp for expiration
        - Check nonce for replay attacks

        Args:
            secret_key: Secret key for verification

        Returns:
            True if signature is valid, False otherwise
        """
        # Stub implementation - in Week 8, this will do actual verification
        return self.signature == f"stub-signature-for-{self.tool_name}"
