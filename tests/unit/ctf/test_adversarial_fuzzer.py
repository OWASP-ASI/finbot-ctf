"""
Tests for the adversarial detector-coverage fuzzer (tools/adversarial_fuzzer).

These run fully offline ($0, no LLM): each scenario spins up its own in-memory
SQLite database and runs the real production detectors. They lock in three
things:

  1. the fuzzer runs end-to-end and classifies every scenario,
  2. the detectors DO catch the canonical attacks (no regression),
  3. adversarial enumeration surfaces the known coverage gaps -- over-limit
     invoices that reach "paid" (not "approved"), and inflated payments with no
     steganographic marker -- which the challenge-scoped detectors miss.
"""

import pytest

from tools.adversarial_fuzzer import build_report, generate_scenarios, run_scenario
from tools.adversarial_fuzzer.scenario import MAX_INVOICE_AMOUNT, Scenario


@pytest.mark.unit
def test_scenarios_are_generated_and_labelled():
    scenarios = generate_scenarios()
    assert len(scenarios) > 0
    # Both attack and benign cases must exist for the oracle to be meaningful.
    assert any(s.is_attack for s in scenarios)
    assert any(not s.is_attack for s in scenarios)


@pytest.mark.unit
def test_canonical_threshold_bypass_is_caught():
    """An approved, over-limit invoice must be flagged (true positive)."""
    scenario = Scenario(
        id="probe-itb",
        family="invoice_decision",
        levers={
            "amount": MAX_INVOICE_AMOUNT + 1,
            "status": "approved",
            "decision_type": "approval",
        },
        is_attack=True,
        asi="ASI01",
    )
    result = run_scenario(scenario)
    assert result.detected is True


@pytest.mark.unit
def test_canonical_inflated_payment_is_caught():
    """An overpayment delivered via hidden text must be flagged."""
    scenario = Scenario(
        id="probe-inf",
        family="payment_transfer",
        levers={"invoice_amount": 1000, "transfer_amount": 1500, "hidden_text": True},
        is_attack=True,
        asi="ASI02",
    )
    result = run_scenario(scenario)
    assert result.detected is True


@pytest.mark.unit
def test_report_runs_and_has_no_false_positives():
    """Full sweep: detectors must never flag a benign scenario."""
    report = build_report()
    assert len(report.results) == len(generate_scenarios())
    assert report.counts["false_positive"] == 0, (
        "a benign scenario was flagged as an attack: "
        f"{[r.scenario.id for r in report.false_positives]}"
    )


@pytest.mark.unit
def test_coverage_gaps_are_surfaced():
    """Adversarial enumeration must surface uncovered attack variants."""
    report = build_report()
    gap_ids = {r.scenario.id for r in report.gaps}

    # Over-limit invoice that reached "paid" (detector keys on "approved").
    assert any(gid.startswith(f"inv:{MAX_INVOICE_AMOUNT + 1}:paid") for gid in gap_ids)
    assert any("inv:120000:paid" in gid for gid in gap_ids)

    # Inflated payment with NO steganographic marker (detector requires one).
    assert "pay:1500:hidden_0" in gap_ids
