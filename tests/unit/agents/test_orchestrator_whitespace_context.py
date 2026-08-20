# Tests for issue #459: OrchestratorAgent._capture_agent_context uses
# `if summary:` to decide whether to store an upstream agent's task_summary
# for downstream propagation. A whitespace-only string ("   ") is truthy in
# Python, so it passes the guard and gets appended to _workflow_context,
# then injected verbatim into every subsequent agent's task description via
# _enrich_with_prior_context -- pure noise, and (per the issue) a guard that
# a prompt-injection payload could exploit by hiding behind a
# content-free-but-non-empty string.
#
# Verified against current source before writing this: line numbers in the
# issue (421-422) match exactly, and this is the sole call site of the
# `if summary:` guard -- all 6 delegation methods (onboarding, invoice,
# fraud, payments, system_maintenance, communication) funnel through this
# one method, so fixing it here fixes all 6, not just one.
#
# No existing test file covered OrchestratorAgent at all before this one.

import pytest

from finbot.agents.orchestrator import OrchestratorAgent
from finbot.core.auth.session import session_manager


@pytest.fixture()
def session(db):
    return session_manager.create_session(email="orch_whitespace@example.com")


def _make_orchestrator(session) -> OrchestratorAgent:
    return OrchestratorAgent(session_context=session)


class TestCaptureAgentContextWhitespaceGuard:

    @pytest.mark.unit
    def test_whitespace_only_summary_not_captured(self, db, session):
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context("invoice_agent", {"task_summary": "   "})
        assert orchestrator._workflow_context == []

    @pytest.mark.unit
    def test_empty_string_summary_not_captured(self, db, session):
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context("invoice_agent", {"task_summary": ""})
        assert orchestrator._workflow_context == []

    @pytest.mark.unit
    def test_missing_summary_key_not_captured(self, db, session):
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context("invoice_agent", {})
        assert orchestrator._workflow_context == []

    @pytest.mark.unit
    def test_tab_and_newline_only_summary_not_captured(self, db, session):
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context("invoice_agent", {"task_summary": "\t\n  \n"})
        assert orchestrator._workflow_context == []

    @pytest.mark.unit
    def test_real_summary_still_captured(self, db, session):
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context(
            "invoice_agent", {"task_summary": "Invoice #123 approved"}
        )
        assert orchestrator._workflow_context == [
            ("invoice_agent", "Invoice #123 approved")
        ]

    @pytest.mark.unit
    def test_non_string_summary_not_captured_and_does_not_raise(self, db, session):
        """task_summary is schema-typed as a string under a strict LLM tool
        call today (base.py's complete_task schema, strict=True), so this
        is currently unreachable via the real call path -- but the guard
        shouldn't rely on an external API contract alone to stay crash-safe.
        Before this test was added, a truthy non-string here would have hit
        `.strip()` on a non-str and raised AttributeError instead of just
        skipping storage."""
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context("invoice_agent", {"task_summary": 123})
        assert orchestrator._workflow_context == []
        orchestrator._capture_agent_context(
            "invoice_agent", {"task_summary": ["not", "a", "string"]}
        )
        assert orchestrator._workflow_context == []

    @pytest.mark.unit
    def test_summary_with_surrounding_whitespace_still_captured_verbatim(
        self, db, session
    ):
        """The fix only needs to reject whitespace-ONLY summaries -- a real
        summary with incidental leading/trailing whitespace should still be
        captured, and captured verbatim (not silently re-stripped), since
        stripping wasn't asked for and could alter meaning downstream."""
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context(
            "invoice_agent", {"task_summary": "  Invoice #123 approved  "}
        )
        assert orchestrator._workflow_context == [
            ("invoice_agent", "  Invoice #123 approved  ")
        ]


class TestEnrichWithPriorContextIntegration:
    """Confirms the fix closes the propagation path end to end, not just
    the storage point in isolation."""

    @pytest.mark.unit
    def test_whitespace_only_summary_never_reaches_downstream_task_description(
        self, db, session
    ):
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context("invoice_agent", {"task_summary": "   "})
        enriched = orchestrator._enrich_with_prior_context("Process the next task")
        assert enriched == "Process the next task"

    @pytest.mark.unit
    def test_mixed_real_and_whitespace_summaries_only_real_one_propagates(
        self, db, session
    ):
        orchestrator = _make_orchestrator(session)
        orchestrator._capture_agent_context("fraud_agent", {"task_summary": "   "})
        orchestrator._capture_agent_context(
            "invoice_agent", {"task_summary": "Invoice #123 approved"}
        )
        enriched = orchestrator._enrich_with_prior_context("Process the next task")
        assert "[fraud_agent]" not in enriched
        assert "[invoice_agent]: Invoice #123 approved" in enriched
