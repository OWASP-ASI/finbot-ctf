"""CLI entrypoint: ``uv run python -m tools.adversarial_fuzzer``."""

from __future__ import annotations

import sys

from .coverage import build_report


def main() -> int:
    report = build_report()
    print(report.render())
    # Exit non-zero when coverage gaps exist, so this can gate CI if desired.
    return 1 if report.gaps else 0


if __name__ == "__main__":
    sys.exit(main())
