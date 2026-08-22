"""
Apply an MCP supply-chain environment preset to a namespace.

Presets live in finbot/ctf/scenarios/mcp_supply_chain/. Use them to switch
between a clean baseline and known compromised tool/policy configurations.

Usage:
    python scripts/apply_mcp_scenario.py list
    python scripts/apply_mcp_scenario.py apply benign --namespace default
    python scripts/apply_mcp_scenario.py apply scorched_earth --namespace default
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.ctf.scenarios.loader import MCPScenarioLoader


def _make_namespace_context(namespace: str) -> SessionContext:
    now = datetime.now(UTC)
    return SessionContext(
        session_id="cli-apply-mcp-scenario",
        user_id="cli",
        is_temporary=True,
        namespace=namespace,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        csrf_token="cli",
    )


def cmd_list(_: argparse.Namespace) -> int:
    loader = MCPScenarioLoader()
    for summary in loader.list_scenarios():
        linked = ", ".join(summary.linked_challenges) or "—"
        print(
            f"{summary.id:20} [{summary.variant:9}] ui={summary.ui_mode:7} "
            f"{summary.title}  (challenges: {linked})"
        )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    loader = MCPScenarioLoader()
    ctx = _make_namespace_context(args.namespace)
    with db_session() as db:
        result = loader.apply(args.scenario_id, ctx, db)

    print(
        f"Applied '{result['title']}' ({result['variant']}) "
        f"to namespace '{args.namespace}'."
    )
    if result["applied_override_servers"]:
        print(f"  Overrides set:  {', '.join(result['applied_override_servers'])}")
    if result["reset_override_servers"]:
        print(f"  Overrides reset: {', '.join(result['reset_override_servers'])}")
    if result["applied_config_servers"]:
        print(f"  Policy set:     {', '.join(result['applied_config_servers'])}")
    if result["reset_config_servers"]:
        print(f"  Policy reset:   {', '.join(result['reset_config_servers'])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply MCP supply-chain environment presets."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List available environment presets")

    apply_parser = sub.add_parser("apply", help="Apply an environment preset")
    apply_parser.add_argument("scenario_id", help="Preset id (e.g. scorched_earth)")
    apply_parser.add_argument(
        "--namespace",
        default="default",
        help="Target namespace (default: default)",
    )

    args = parser.parse_args()
    if args.command == "list":
        return cmd_list(args)
    if args.command == "apply":
        try:
            return cmd_apply(args)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
