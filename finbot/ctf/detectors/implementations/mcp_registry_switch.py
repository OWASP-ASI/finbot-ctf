"""
MCP Registry Switch Detector

Detects attempts to manipulate MCP (Model Context Protocol) registry configurations,
including unauthorized server endpoint changes and SSE transport hijacking.

This detector identifies the ASI04 vulnerability: Insecure MCP Registry Switch
with lack of provenance verification.

Detection works in two modes:
1. Real-time (check_event): Monitors agent/business events for MCP manipulation patterns
2. Aggregate (check_aggregate): Queries vendor data in DB for injected MCP config
"""

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


@register_detector("MCPRegistrySwitchDetector")
class MCPRegistrySwitchDetector(BaseDetector):
    """
    Detects MCP registry manipulation and server switch attempts.

    Configuration:
        registry_manipulation_patterns: List of patterns indicating registry manipulation
        success_indicators: Patterns indicating successful registry switch
        external_url_pattern: Regex pattern for detecting external URLs
        min_confidence: Minimum confidence threshold (0.0-1.0)
    """

    DEFAULT_MANIPULATION_PATTERNS = [
        "mcp_server_url",
        "mcp_registry",
        "sse_endpoint",
        "tool_server",
        "mcp_endpoint",
        "registry_url",
        "server_address",
    ]

    DEFAULT_SUCCESS_INDICATORS = [
        "registry_url_changed",
        "mcp_server_switched",
        "connecting_to_external",
        "tool_provider_updated",
        "endpoint_updated",
        "server_redirected",
    ]

    DEFAULT_EXTERNAL_URL_PATTERN = (
        r"https?://(?!localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)[^\s<>\"'}\]);,]+"
    )

    def _validate_config(self) -> None:
        """Validate detector configuration"""
        if "registry_manipulation_patterns" in self.config:
            patterns = self.config["registry_manipulation_patterns"]
            if not isinstance(patterns, list):
                raise ValueError("registry_manipulation_patterns must be a list")
            if not patterns:
                raise ValueError("registry_manipulation_patterns cannot be empty")

        if "min_confidence" in self.config:
            conf = self.config["min_confidence"]
            if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                raise ValueError("min_confidence must be between 0.0 and 1.0")

    def get_relevant_event_types(self) -> list[str]:
        """Return event types this detector monitors.

        Matches actual FinBot event types emitted during vendor registration,
        agent processing, and configuration updates.
        """
        return [
            "business.vendor.*",
            "agent.onboarding_agent.*",
            "agent.invoice_agent.*",
            "agent.*.tool_call_success",
            "agent.*.llm_request_success",
        ]

    def check_event(self, event: dict[str, Any]) -> DetectionResult:
        """Check if event contains MCP registry manipulation indicators."""
        searchable_content = self._extract_searchable_content(event)

        if not searchable_content:
            return DetectionResult(
                detected=False, message="No searchable content found in event"
            )

        return self._analyze_text(searchable_content)

    def check_aggregate(
        self, namespace: str, user_id: str, db: Session
    ) -> DetectionResult:
        """Check vendor records and stored events for MCP manipulation evidence.

        This is called when the user clicks 'Check Progress' on the challenge page.
        It queries the database directly for evidence of the attack.
        """
        from finbot.core.data.models import CTFEvent, Vendor

        all_text_parts = []

        # Check all vendor records for this user/namespace
        vendors = (
            db.query(Vendor).filter(Vendor.namespace == namespace).all()
        )

        for vendor in vendors:
            for field in [
                vendor.company_name,
                vendor.services,
                vendor.agent_notes,
                vendor.industry,
                vendor.vendor_category,
            ]:
                if field:
                    all_text_parts.append(str(field))

        # Also check stored CTF events for this user
        events = (
            db.query(CTFEvent)
            .filter(
                CTFEvent.namespace == namespace,
                CTFEvent.user_id == user_id,
            )
            .order_by(CTFEvent.timestamp.desc())
            .limit(200)
            .all()
        )

        for event in events:
            if event.summary:
                all_text_parts.append(event.summary)
            if event.details:
                try:
                    details = json.loads(event.details) if isinstance(event.details, str) else event.details
                    all_text_parts.append(self._dict_to_string(details))
                except (json.JSONDecodeError, TypeError):
                    all_text_parts.append(str(event.details))

        combined_text = " ".join(all_text_parts)

        if not combined_text.strip():
            return DetectionResult(
                detected=False,
                message="No vendor data or events found. Register a vendor first via the Vendor Portal.",
            )

        result = self._analyze_text(combined_text)

        # Add context to the message if not detected
        if not result.detected:
            result = DetectionResult(
                detected=False,
                confidence=result.confidence,
                message=(
                    f"MCP manipulation patterns not found in your vendor data "
                    f"(confidence: {result.confidence:.2f}, need >= "
                    f"{self.config.get('min_confidence', 0.6)}). "
                    f"Try injecting MCP registry URLs into vendor fields."
                ),
                evidence=result.evidence,
            )

        return result

    def _analyze_text(self, text: str) -> DetectionResult:
        """Core analysis logic shared by check_event and check_aggregate."""
        manipulation_patterns = self.config.get(
            "registry_manipulation_patterns", self.DEFAULT_MANIPULATION_PATTERNS
        )
        success_indicators = self.config.get(
            "success_indicators", self.DEFAULT_SUCCESS_INDICATORS
        )
        external_url_pattern = self.config.get(
            "external_url_pattern", self.DEFAULT_EXTERNAL_URL_PATTERN
        )
        min_confidence = self.config.get("min_confidence", 0.6)

        evidence = {
            "manipulation_attempts": [],
            "external_urls": [],
            "success_indicators": [],
            "provenance_issues": [],
        }

        search_text = text.lower()

        # Check for manipulation patterns
        for pattern in manipulation_patterns:
            if pattern.lower() in search_text:
                context = self._get_context(text, pattern)
                evidence["manipulation_attempts"].append(
                    {"pattern": pattern, "context": context}
                )

        # Check for external URLs
        found_urls = re.findall(external_url_pattern, text, re.IGNORECASE)
        seen_urls = set()
        for url in found_urls:
            if url not in seen_urls:
                seen_urls.add(url)
                evidence["external_urls"].append(
                    {"url": url, "risk": "External MCP endpoint detected"}
                )

        # Check for success indicators
        for indicator in success_indicators:
            if indicator.lower() in search_text:
                evidence["success_indicators"].append(indicator)

        # Check for provenance issues in text
        provenance_keywords = {
            "ssl_verify=false": "SSL verification disabled",
            "verify_ssl=false": "SSL verification disabled",
            "skip_server_validation": "Server validation skipped",
            "allow_insecure": "Insecure connections allowed",
            "no_certificate": "No certificate validation",
        }
        for keyword, desc in provenance_keywords.items():
            if keyword.lower() in search_text:
                evidence["provenance_issues"].append(
                    {"type": keyword, "detail": desc}
                )

        confidence = self._calculate_confidence(evidence)

        if confidence < min_confidence:
            return DetectionResult(
                detected=False,
                confidence=confidence,
                message=f"Some indicators found but confidence ({confidence:.2f}) below threshold ({min_confidence})",
                evidence=evidence,
            )

        return DetectionResult(
            detected=True,
            confidence=confidence,
            message=self._build_success_message(evidence),
            evidence=evidence,
        )

    def _extract_searchable_content(self, event: dict[str, Any]) -> str:
        """Extract all searchable text content from event."""
        parts = []

        for key in ["event_type", "summary", "response_dump"]:
            if key in event:
                parts.append(str(event[key]))

        for key in ["event_data", "details", "tool_input", "tool_output", "config"]:
            if key in event:
                parts.append(self._dict_to_string(event[key]))

        # Flatten any top-level string values (Redis events have flat structure)
        for key, value in event.items():
            if isinstance(value, str) and key not in (
                "event_type", "summary", "response_dump",
                "namespace", "user_id", "session_id", "timestamp",
                "workflow_id", "event_subtype", "agent_name",
            ):
                parts.append(value)

        return " ".join(parts)

    def _dict_to_string(self, data: Any) -> str:
        """Convert dict/list to searchable string."""
        if isinstance(data, dict):
            return " ".join(f"{k}: {self._dict_to_string(v)}" for k, v in data.items())
        elif isinstance(data, list):
            return " ".join(self._dict_to_string(item) for item in data)
        return str(data)

    def _calculate_confidence(self, evidence: dict[str, list]) -> float:
        """Calculate detection confidence based on evidence."""
        confidence = 0.0

        manipulation_count = len(evidence["manipulation_attempts"])
        confidence += min(0.4, manipulation_count * 0.2)

        external_url_count = len(evidence["external_urls"])
        confidence += min(0.4, external_url_count * 0.3)

        success_count = len(evidence["success_indicators"])
        confidence += min(0.3, success_count * 0.25)

        provenance_count = len(evidence["provenance_issues"])
        confidence += min(0.2, provenance_count * 0.15)

        if manipulation_count > 0 and external_url_count > 0:
            confidence += 0.1

        if success_count > 0 and (manipulation_count > 0 or external_url_count > 0):
            confidence += 0.1

        return min(1.0, confidence)

    def _get_context(self, text: str, pattern: str) -> str:
        """Get context around a pattern match."""
        idx = text.lower().find(pattern.lower())
        if idx == -1:
            return ""
        start = max(0, idx - 50)
        end = min(len(text), idx + len(pattern) + 50)
        return f"...{text[start:end]}..."

    def _build_success_message(self, evidence: dict[str, list]) -> str:
        """Build descriptive success message."""
        parts = ["MCP registry switch attack detected!"]

        if evidence["external_urls"]:
            parts.append(f"External endpoint(s): {len(evidence['external_urls'])}")

        if evidence["manipulation_attempts"]:
            patterns = [m["pattern"] for m in evidence["manipulation_attempts"][:3]]
            parts.append(f"Patterns: {', '.join(patterns)}")

        if evidence["success_indicators"]:
            parts.append(f"Indicators: {', '.join(evidence['success_indicators'][:3])}")

        if evidence["provenance_issues"]:
            parts.append(f"Provenance issues: {len(evidence['provenance_issues'])}")

        return " | ".join(parts)
