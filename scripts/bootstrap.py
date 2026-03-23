"""
Bootstrap

One-time startup tasks: run migrations, seed CC admins, clean up
expired sessions and old analytics, load CTF definitions from YAML.
Every operation is idempotent and safe to call repeatedly.

Called automatically by run.py (local dev) and docker/entrypoint.sh
(Docker). You should not need to run this manually.

Audience: Core setup — called automatically at startup.

Usage:
    python scripts/bootstrap.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from alembic import command
from alembic.config import Config

from finbot.config import settings

ALEMBIC_INI = str(project_root / "alembic.ini")


def run_bootstrap() -> None:
    """Execute all one-time startup tasks in order.

    Safe to call repeatedly — every operation is idempotent — but should
    run exactly once per deployment, *before* any uvicorn workers start.
    """
    _run_migrations()
    _seed_cc_admins()
    _cleanup_expired_sessions()
    _cleanup_old_analytics()
    _load_ctf_definitions()


def _run_migrations() -> None:
    print(f"⏫ Running migrations ({settings.DATABASE_TYPE})...")
    try:
        cfg = Config(ALEMBIC_INI)
        command.upgrade(cfg, "head")
        print("✅ Migrations complete")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ Migration failed: {e}")
        print("   Falling back to create_tables()")
        from finbot.core.data.database import create_tables  # pylint: disable=import-outside-toplevel

        create_tables()


def _seed_cc_admins() -> None:
    if not settings.CC_ENABLED:
        return
    try:
        from finbot.apps.cc.auth import seed_admins_from_env  # pylint: disable=import-outside-toplevel

        seeded = seed_admins_from_env()
        if seeded > 0:
            print(f"🔑 Seeded {seeded} CC admins from env")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️ CC admin seeding skipped: {e}")


def _cleanup_expired_sessions() -> None:
    try:
        from finbot.core.auth.session import session_manager  # pylint: disable=import-outside-toplevel

        cleaned = session_manager.cleanup_expired_sessions()
        if cleaned > 0:
            print(f"🧹 Cleaned up {cleaned} expired sessions")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️ Session cleanup skipped: {e}")


def _cleanup_old_analytics() -> None:
    if not settings.CC_ANALYTICS_ENABLED:
        return
    try:
        from finbot.core.analytics.retention import cleanup_old_pageviews  # pylint: disable=import-outside-toplevel

        cleaned = cleanup_old_pageviews()
        if cleaned > 0:
            print(f"📊 Cleaned up {cleaned} old pageviews (>{settings.ANALYTICS_RETENTION_DAYS}d)")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️ Analytics cleanup skipped: {e}")


def _load_ctf_definitions() -> None:
    try:
        from finbot.ctf.definitions.loader import load_definitions_on_startup  # pylint: disable=import-outside-toplevel

        result = load_definitions_on_startup()
        print(
            f"🎯 CTF loaded: {len(result['challenges'])} challenges, "
            f"{len(result['badges'])} badges"
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"⚠️ CTF definition loading failed: {e}")


if __name__ == "__main__":
    run_bootstrap()
