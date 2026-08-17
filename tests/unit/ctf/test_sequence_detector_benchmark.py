"""Benchmark: SequenceDetector session-window query latency.

Seeds 1,000 CTFEvent rows for one session into an in-memory SQLite database
(with the composite index from the migration) and measures p95 query latency
for check_event. Target: p95 < 10ms.

SQLite is used here as a structural proxy — the index design and query shape
are what matter. PostgreSQL performance will be better due to WAL and buffer
cache. This test catches regressions in the query path (e.g. missing index,
full-table scan, N+1 loading).
"""

import json
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Index, create_engine, text
from sqlalchemy.orm import sessionmaker

from finbot.core.data.database import Base
from finbot.core.data.models import CTFEvent
from finbot.ctf.detectors.primitives.sequence_detector import SequenceDetector

BENCHMARK_ROWS = 1000
BENCHMARK_RUNS = 100
P95_LIMIT_MS = 10.0


@pytest.fixture(scope="module")
def bench_db():
    """In-memory SQLite with composite index and 1,000 CTFEvent rows."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)

    # Create the composite index from the migration
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_ctf_event_session_ts_type "
                "ON ctf_events (session_id, timestamp, event_type)"
            )
        )
        conn.commit()

    Session = sessionmaker(bind=engine)
    session = Session()

    namespace = "bench-ns"
    session_id = "bench-session-001"
    base_time = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)

    rows = []
    for i in range(BENCHMARK_ROWS):
        # Alternate between two event types so the matching step is near the end
        event_type = (
            "agent.fraud.tool_call_success" if i % 2 == 0
            else "agent.payments.tool_call_success"
        )
        rows.append(
            CTFEvent(
                external_event_id=str(uuid.uuid4()),
                namespace=namespace,
                user_id="bench-user",
                session_id=session_id,
                workflow_id="bench-wf",
                vendor_id=None,
                event_category="agent",
                event_type=event_type,
                summary=f"event {i}",
                details=json.dumps({"tool_name": "approve_invoice", "seq": i}),
                severity="info",
                tool_name="approve_invoice",
                timestamp=base_time + timedelta(seconds=i),
            )
        )

    session.bulk_save_objects(rows)
    session.commit()

    yield session, namespace, session_id

    session.close()
    Base.metadata.drop_all(bind=engine)


def test_session_window_query_p95(bench_db):
    """p95 latency for check_event over 1,000-row session must be < 10ms."""
    session, namespace, session_id = bench_db

    det = SequenceDetector(
        "bench-challenge",
        config={
            "steps": [
                {
                    "event_type": "agent.*.tool_call_success",
                    "conditions": {"tool_name": "approve_invoice"},
                    "label": "Payment 1",
                },
                {
                    "event_type": "agent.*.tool_call_success",
                    "conditions": {"tool_name": "approve_invoice"},
                    "label": "Payment 2",
                },
            ],
            "within_n_events": 1000,
            "order_matters": True,
            "window": "session",
        },
    )

    trigger_event = {
        "event_type": "agent.fraud.tool_call_success",
        "namespace": namespace,
        "session_id": session_id,
        "workflow_id": "bench-wf",
        "timestamp": "2026-06-01T00:20:00Z",
    }

    import asyncio

    latencies_ms: list[float] = []
    for _ in range(BENCHMARK_RUNS):
        t0 = time.perf_counter()
        asyncio.get_event_loop().run_until_complete(
            det.check_event(trigger_event, session)
        )
        latencies_ms.append((time.perf_counter() - t0) * 1000)

    latencies_ms.sort()
    p95 = latencies_ms[int(BENCHMARK_RUNS * 0.95)]
    p50 = statistics.median(latencies_ms)

    print(f"\nSequenceDetector benchmark ({BENCHMARK_ROWS} rows, {BENCHMARK_RUNS} runs)")
    print(f"  p50: {p50:.2f}ms   p95: {p95:.2f}ms   limit: {P95_LIMIT_MS}ms")

    assert p95 < P95_LIMIT_MS, (
        f"p95 latency {p95:.2f}ms exceeds {P95_LIMIT_MS}ms limit. "
        f"Check that idx_ctf_event_session_ts_type is applied."
    )
