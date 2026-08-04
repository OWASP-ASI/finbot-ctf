"""Benchmark: CanaryDetector pattern-matching throughput.

This test verifies pattern matching across 10,000 events; no regression against
baseline event processing rate." Measures check_event() throughput over a
mixed batch of clean and canary-tripped events and asserts a floor rate,
so a future change to the sentinel regex (e.g. catastrophic backtracking)
gets caught here instead of in production.
"""

import asyncio
import json
import time

import pytest

from finbot.ctf.detectors.implementations.canary_detector import CanaryDetector

EVENT_COUNT = 10_000
MIN_EVENTS_PER_SEC = 5_000  # generous floor; regex is a single non-backtracking scan


def _event(i: int) -> dict:
    """Every 10th event carries a canary sentinel; the rest are clean."""
    if i % 10 == 0:
        payload = {"tin": f"CANARY_TIN_{i:04d}"}
    else:
        payload = {"tin": f"{i:02d}-{i:07d}", "company": f"Vendor {i}"}
    return {
        "event_type": "agent.fraud_agent.tool_call_success",
        "agent_name": "fraud_agent",
        "tool_name": "get_vendor_details",
        "namespace": "bench",
        "tool_result": json.dumps(payload),
    }


def test_canary_detector_throughput():
    detector = CanaryDetector("bench-challenge", {})
    events = [_event(i) for i in range(EVENT_COUNT)]

    loop = asyncio.new_event_loop()
    try:
        t0 = time.perf_counter()
        for evt in events:
            loop.run_until_complete(detector.check_event(evt, None))
        elapsed = time.perf_counter() - t0
    finally:
        loop.close()

    rate = EVENT_COUNT / elapsed
    print(f"\nCanaryDetector benchmark: {EVENT_COUNT} events in {elapsed:.3f}s ({rate:.0f} events/sec)")

    assert rate > MIN_EVENTS_PER_SEC, (
        f"CanaryDetector throughput {rate:.0f} events/sec fell below the "
        f"{MIN_EVENTS_PER_SEC} floor -- check for regex backtracking regressions."
    )


@pytest.mark.asyncio
async def test_canary_detector_correctness_at_scale():
    """Every 10th event (the ones seeded with a sentinel) must fire; the rest must not."""
    detector = CanaryDetector("bench-challenge", {})
    fired = 0
    for i in range(1000):
        result = await detector.check_event(_event(i), None)
        if result.detected:
            fired += 1
    assert fired == 100  # exactly the i % 10 == 0 events
