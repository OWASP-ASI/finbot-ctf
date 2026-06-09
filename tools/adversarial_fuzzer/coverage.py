"""
Coverage / gap report.

Cross every generated scenario against its detector and classify the outcome
using the oracle label:

    is_attack  detected   classification
    --------------------------------------
    True       True       true_positive   (detector caught a real attack)
    True       False      FALSE NEGATIVE  (coverage GAP -- the interesting bit)
    False      False      true_negative   (correctly ignored benign input)
    False      True       false_positive  (benign input wrongly flagged)

False negatives are uncovered attack variants -- attacks an adversary could run
that the current, challenge-scoped detectors do not flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .harness import RunResult, run_scenario
from .scenario import Scenario, generate_scenarios


@dataclass
class CoverageReport:
    results: list[RunResult] = field(default_factory=list)

    def _bucket(self, run: RunResult) -> str:
        attack = run.scenario.is_attack
        if attack and run.detected:
            return "true_positive"
        if attack and not run.detected:
            return "false_negative"
        if not attack and not run.detected:
            return "true_negative"
        return "false_positive"

    @property
    def counts(self) -> dict[str, int]:
        out = {
            "true_positive": 0,
            "false_negative": 0,
            "true_negative": 0,
            "false_positive": 0,
        }
        for run in self.results:
            out[self._bucket(run)] += 1
        return out

    @property
    def gaps(self) -> list[RunResult]:
        """Attacks that no detector flagged (the actionable findings)."""
        return [r for r in self.results if self._bucket(r) == "false_negative"]

    @property
    def false_positives(self) -> list[RunResult]:
        return [r for r in self.results if self._bucket(r) == "false_positive"]

    def render(self) -> str:
        c = self.counts
        attacks = c["true_positive"] + c["false_negative"]
        lines: list[str] = []
        lines.append("=" * 70)
        lines.append("  FinBot adversarial detector-coverage report")
        lines.append("=" * 70)
        # We deliberately do NOT headline a "caught %" -- the oracle is broader
        # than any single challenge-scoped detector, so a ratio would be a
        # misleading score. The signal is the SPECIFIC uncovered variants below.
        lines.append(f"  scenarios generated      : {len(self.results)}")
        lines.append(f"  policy violations (oracle): {attacks}")
        lines.append(f"  uncovered variants (FN)  : {c['false_negative']}")
        lines.append(f"  false positives          : {c['false_positive']}")
        lines.append("-" * 70)

        if self.gaps:
            lines.append("  UNCOVERED ATTACK VARIANTS (no detector fired):")
            for r in self.gaps:
                lines.append(
                    f"    [{r.scenario.asi}] {r.scenario.id}\n"
                    f"        {r.scenario.rationale}\n"
                    f"        target detector: {r.detector_name} "
                    "(may be intentionally challenge-scoped)"
                )
        else:
            lines.append("  No coverage gaps found in the generated space.")

        if self.false_positives:
            lines.append("-" * 70)
            lines.append("  FALSE POSITIVES (benign flagged as attack):")
            for r in self.false_positives:
                lines.append(f"    {r.scenario.id} -> {r.detector_name}")

        lines.append("=" * 70)
        return "\n".join(lines)


def build_report(scenarios: list[Scenario] | None = None) -> CoverageReport:
    """Run every scenario and assemble the coverage report."""
    scenarios = scenarios if scenarios is not None else generate_scenarios()
    results = [run_scenario(s) for s in scenarios]
    return CoverageReport(results=results)
