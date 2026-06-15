"""
Adversarial detector coverage fuzzer for OWASP FinBot CTF.

A small, offline ($0, no LLM) port of the genesis-adversary search idea:
enumerate adversarial *scenarios* over a lever vocabulary, label each one with
a detector-independent business/OWASP policy oracle, materialize it into the
real FinBot data model + event stream, run the production detectors against it,
and report where genuine attack variants slip past every detector.

The point is not to re-detect what detectors already catch -- it is to surface
*uncovered* attack variants (false negatives) that adversarial enumeration finds
but the current, challenge-scoped detectors do not flag.
"""

from .coverage import CoverageReport, build_report
from .harness import RunResult, run_scenario
from .scenario import Scenario, generate_scenarios

__all__ = [
    "Scenario",
    "generate_scenarios",
    "RunResult",
    "run_scenario",
    "CoverageReport",
    "build_report",
]
