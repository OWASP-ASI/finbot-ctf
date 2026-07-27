# ============================================================
# File: finbot/aegis/harness/benchmark.py
# Purpose: Detector precision/recall/F1 utilities for red-team harness
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 8
# OWASP Category: ASI09 Human Trust Exploitation (measurement)
# ============================================================
"""Red-team harness: detector precision/recall/F1."""

from dataclasses import dataclass


@dataclass
class DetectorBenchmarkResult:
    detector_id: str
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int


def compute_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )
    return precision, recall, f1


def benchmark_detector(
    detector_id: str,
    predictions: list[bool],
    ground_truth: list[bool],
) -> DetectorBenchmarkResult:
    tp = sum(1 for p, g in zip(predictions, ground_truth, strict=True) if p and g)
    fp = sum(1 for p, g in zip(predictions, ground_truth, strict=True) if p and not g)
    fn = sum(1 for p, g in zip(predictions, ground_truth, strict=True) if not p and g)
    precision, recall, f1 = compute_f1(tp, fp, fn)
    return DetectorBenchmarkResult(
        detector_id=detector_id,
        precision=precision,
        recall=recall,
        f1=f1,
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
    )
