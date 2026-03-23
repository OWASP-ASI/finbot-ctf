"""
Reload CTF Definitions

Re-reads challenge (and optionally badge) YAML files from
finbot/ctf/definitions/ and upserts them into the database.
Use this on a running server to sync definition changes
without restarting the application.

Audience: Production ops — run after editing YAML definitions.

Usage:
    python scripts/reload_challenges.py           # challenges only
    python scripts/reload_challenges.py --badges  # challenges + badges
    python scripts/reload_challenges.py -q        # quiet (counts only)
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from finbot.ctf.definitions.loader import get_loader
from finbot.core.data.database import db_session


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reload CTF definitions from YAML into the database."
    )
    parser.add_argument(
        "--badges",
        action="store_true",
        help="Also reload badge definitions (default: challenges only)",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only print counts, no extra messages",
    )
    args = parser.parse_args()

    loader = get_loader()
    with db_session() as db:
        if args.badges:
            result = loader.load_all(db)
            challenges_count = len(result["challenges"])
            badges_count = len(result["badges"])
            if args.quiet:
                print(f"{challenges_count} {badges_count}")
            else:
                print(
                    f"Reloaded {challenges_count} challenges, {badges_count} badges."
                )
        else:
            loaded = loader.load_challenges(db)
            count = len(loaded)
            if args.quiet:
                print(count)
            else:
                print(f"Reloaded {count} challenges.")


if __name__ == "__main__":
    main()
