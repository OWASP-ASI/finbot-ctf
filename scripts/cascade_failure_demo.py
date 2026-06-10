"""Cascade failure demo for the FinBot multi-agent invoice pipeline.

Seeds a demo vendor and submits a series of invoices that exercise the four
canonical cascade-failure scenarios (dirty data, half-cascade, mid-chain,
full cascade) through the real orchestrator + specialized agent chain.

Runs the agents in-process (no HTTP / no auth) so it works as a standalone
research script. Prints, for each scenario:
    * the invoice payload
    * the agent chain with per-step success / confidence / errors
    * aggregate cascade analysis and inferred cascade type

Usage:
    uv run python scripts/cascade_failure_demo.py

Requires:
    * OPENAI_API_KEY (or Ollama) configured in .env
    * Database initialised (run scripts/db.py setup once)
"""

import asyncio
import secrets
import sys
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from finbot.agents.cascade import load_scenarios_file, run_cascade_orchestrator
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.core.data.repositories import InvoiceRepository, VendorRepository
from finbot.core.messaging import event_bus


async def _ping_redis() -> bool:
    try:
        await event_bus.redis.ping()
        return True
    except Exception:  # pylint: disable=broad-exception-caught
        return False


async def _noop(*_args, **_kwargs) -> None:
    return None


async def _ensure_event_bus() -> None:
    """Disable Redis event emission if Redis isn't reachable.

    The orchestrator and every specialised agent publish events to Redis on
    each iteration. For the standalone demo script we don't need that stream,
    and requiring the user to run Redis just to watch the cascade would be
    hostile. If ping fails, replace the emit methods with no-ops so the agent
    loop continues uninterrupted.
    """
    if await _ping_redis():
        print("Redis: connected (events will be emitted)")
        return
    print(
        "Redis: unreachable -- event emission disabled for this demo run. "
        "The agent chain itself will still run normally."
    )
    event_bus.emit_agent_event = _noop  # type: ignore[assignment]
    event_bus.emit_business_event = _noop  # type: ignore[assignment]


DEMO_NAMESPACE = "cascade-demo"
DEMO_USER_ID = "cascade_demo_user"


def _build_session(vendor_id: int | None = None) -> SessionContext:
    """Construct a SessionContext for in-process agent invocation."""
    now = datetime.now(UTC)
    return SessionContext(
        session_id=f"sess_{secrets.token_urlsafe(12)}",
        user_id=DEMO_USER_ID,
        is_temporary=False,
        namespace=DEMO_NAMESPACE,
        created_at=now,
        expires_at=now + timedelta(hours=2),
        email="cascade-demo@example.com",
        portal_type="vendor",
        current_vendor_id=vendor_id,
    )


def _ensure_demo_vendor() -> int:
    """Create (or reuse) the demo vendor in the demo namespace."""
    bootstrap = _build_session()
    with db_session() as db:
        repo = VendorRepository(db, bootstrap)
        existing = repo.list_vendors() or []
        for v in existing:
            if v.company_name == "Cascade Demo Vendor":
                return v.id
        vendor = repo.create_vendor(
            company_name="Cascade Demo Vendor",
            vendor_category="Equipment",
            industry="Production",
            services="Equipment rental for demos",
            contact_name="Jane Cascade",
            email=f"cascade-{int(datetime.now().timestamp())}@example.com",
            tin="12-3456789",
            bank_account_number="1234567890",
            bank_name="Demo Bank",
            bank_routing_number="987654321",
            bank_account_holder_name="Cascade Demo Vendor",
            phone="555-CASCADE",
        )
        return vendor.id


def _create_invoice(vendor_id: int, payload: dict[str, Any]) -> int:
    session = _build_session(vendor_id=vendor_id)
    invoice_date = datetime.fromisoformat(payload["invoice_date"]).replace(tzinfo=UTC)
    due_date = datetime.fromisoformat(payload["due_date"]).replace(tzinfo=UTC)
    with db_session() as db:
        repo = InvoiceRepository(db, session)
        invoice = repo.create_invoice_for_current_vendor(
            invoice_number=payload["invoice_number"],
            amount=payload["amount"],
            description=payload["description"],
            invoice_date=invoice_date,
            due_date=due_date,
        )
        return invoice.id


def _print_section(title: str) -> None:
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def _print_cascade_result(result: dict[str, Any]) -> None:
    analysis = result.get("cascade_analysis", {})
    chain = result.get("agent_chain", [])

    print("\nCASCADE ANALYSIS")
    print(f"  cascade_type:              {analysis.get('cascade_type')}")
    print(f"  cascade_failures_detected: {analysis.get('cascade_failures_detected')}")
    print(f"  initial_confidence:        {analysis.get('initial_confidence')}")
    print(f"  final_confidence:          {analysis.get('final_confidence')}")
    print(f"  confidence_degradation:    {analysis.get('confidence_degradation')}")
    print(f"  total_errors:              {analysis.get('total_errors')}")
    print(f"  failed_agents:             {analysis.get('failed_agents')}")
    print(f"  reached_final_agent:       {analysis.get('reached_final_agent')}")

    print("\nAGENT CHAIN")
    if not chain:
        print("  (no agent steps were recorded)")
        return
    for step in chain:
        marker = "[OK]" if step["success"] else "[FAIL]"
        reasoning = textwrap.shorten(step["reasoning"] or "", width=300, placeholder="...")
        print(f"  {step['order']}. {step['agent']} {marker}")
        print(f"     confidence: {step['confidence']}")
        if step["errors"]:
            print(f"     errors:     {', '.join(step['errors'])}")
        print(f"     reasoning:  {reasoning}")


async def _run_scenario(
    vendor_id: int, title: str, payload: dict[str, Any]
) -> None:
    _print_section(title)
    print(f"  invoice_number: {payload['invoice_number']}")
    print(f"  amount:         ${payload['amount']}")
    print(f"  due_date:       {payload['due_date']}")
    print(f"  description:    {textwrap.shorten(payload['description'], width=200)}")

    invoice_id = _create_invoice(vendor_id, payload)
    session = _build_session(vendor_id=vendor_id)
    try:
        result = await run_cascade_orchestrator(
            task_data={
                "invoice_id": invoice_id,
                "vendor_id": vendor_id,
                "description": (
                    "A new invoice has been submitted. Process the invoice and "
                    "notify the vendor of the decision."
                ),
            },
            session_context=session,
            workflow_id=f"cascade_demo_{secrets.token_urlsafe(6)}",
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"\n  ERROR running orchestrator: {type(e).__name__}: {e}")
        return

    _print_cascade_result(result)


def _unique(prefix: str) -> str:
    return f"{prefix}-{int(datetime.now().timestamp() * 1000)}"


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _in_days(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%d")


def _scenarios() -> list[tuple[str, dict[str, Any]]]:
    """Load ordered (title, invoice_payload) scenarios from the JSON file."""
    data = load_scenarios_file()
    result: list[tuple[str, dict[str, Any]]] = []
    for sc in data.get("scenarios", []):
        inv = sc["invoice"]
        payload = {
            "invoice_number": _unique(inv["invoice_prefix"]),
            "amount": float(inv["amount"]),
            "description": inv["description"],
            "invoice_date": _today(),
            "due_date": _in_days(int(inv["due_date_offset_days"])),
        }
        result.append((sc["title"], payload))
    return result


async def _main_async() -> None:
    print("OWASP FinBot - Multi-Agent Cascading Failures Demo")
    print(f"Namespace: {DEMO_NAMESPACE}")

    await _ensure_event_bus()

    vendor_id = _ensure_demo_vendor()
    print(f"Demo vendor id: {vendor_id}")

    for i, (title, payload) in enumerate(_scenarios(), start=1):
        await _run_scenario(vendor_id, f"Scenario {i}: {title}", payload)
        await asyncio.sleep(1)

    _print_section("Demo complete")


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
