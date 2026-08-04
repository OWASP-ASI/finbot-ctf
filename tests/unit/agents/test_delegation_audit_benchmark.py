"""Benchmark: Delegation Audit Service overhead.

This test verifies delegation.context_snapshot emission adds less than 2ms per
delegation call, measured across 100 sequential delegation sequences."

event_bus is mocked (as in test_delegation_audit.py) so this measures the
code-path overhead _emit_delegation_event() itself adds -- context_preview
slicing and building the two event payloads -- not Redis network latency,
which is an infrastructure concern rather than a regression in this code.
"""

import statistics
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

RUNS = 100
MAX_MS_PER_CALL = 2.0


def _make_orchestrator():
    from finbot.agents.orchestrator import OrchestratorAgent

    session_ctx = MagicMock()
    session_ctx.namespace = "bench-ns"
    session_ctx.user_id = "bench-user"
    session_ctx.session_id = "bench-sess"
    session_ctx.current_vendor_id = 1

    with patch("finbot.agents.orchestrator.event_bus"):
        orch = OrchestratorAgent(session_context=session_ctx, workflow_id="bench-wf")
    return orch


@pytest.mark.asyncio
async def test_delegation_audit_overhead():
    orch = _make_orchestrator()
    orch._enrich_with_prior_context("Process payment for vendor 42")

    latencies_ms: list[float] = []
    with patch("finbot.agents.orchestrator.event_bus") as mock_bus:
        mock_bus.emit_agent_event = AsyncMock()
        mock_bus.emit_business_event = AsyncMock()

        for _ in range(RUNS):
            t0 = time.perf_counter()
            await orch._emit_delegation_event(
                "payments_agent", {"task_status": "completed", "task_summary": "Paid invoice #1"}
            )
            latencies_ms.append((time.perf_counter() - t0) * 1000)

    latencies_ms.sort()
    p95 = latencies_ms[int(RUNS * 0.95)]
    mean = statistics.mean(latencies_ms)

    print(f"\nDelegation audit benchmark ({RUNS} calls): mean={mean:.3f}ms p95={p95:.3f}ms limit={MAX_MS_PER_CALL}ms")

    assert mean < MAX_MS_PER_CALL, (
        f"Mean delegation audit overhead {mean:.3f}ms exceeds {MAX_MS_PER_CALL}ms budget."
    )
