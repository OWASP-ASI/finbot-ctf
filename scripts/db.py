"""
Database Management CLI

Alembic-backed database management for FinBot CTF.
Handles initial setup, running/rolling-back migrations,
inspecting migration history, and generating new migrations
from model changes.

Audience: Core setup and development.

Usage:
    python scripts/db.py setup                  # Create DB + run all migrations
    python scripts/db.py migrate                # Run pending migrations
    python scripts/db.py rollback               # Undo the last migration
    python scripts/db.py status                 # Show current revision and history
    python scripts/db.py generate "description" # Auto-generate a new migration
    python scripts/db.py stamp                  # Stamp existing DB at head (no DDL)
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from alembic import command
from alembic.config import Config

from finbot.config import settings
from finbot.core.data.database import get_database_info, test_database_connection

ALEMBIC_INI = str(project_root / "alembic.ini")


def get_alembic_config() -> Config:
    return Config(ALEMBIC_INI)


def ensure_postgresql_database() -> bool:
    """Create the PostgreSQL database if it doesn't exist."""
    try:
        import psycopg2  # pylint: disable=import-outside-toplevel
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT  # pylint: disable=import-outside-toplevel

        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database="postgres",
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{settings.POSTGRES_DB}'"
        )
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE {settings.POSTGRES_DB}")
            print(f"  Database '{settings.POSTGRES_DB}' created")
        else:
            print(f"  Database '{settings.POSTGRES_DB}' already exists")

        cursor.close()
        conn.close()
        return True
    except ImportError:
        print("  psycopg2 is not installed — run: uv sync")
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"  PostgreSQL setup failed: {e}")
        print("  Hint: docker compose up -d postgres")
        return False


def cmd_setup() -> None:
    """Full setup: ensure database exists, then run all migrations."""
    print(f"Setting up {settings.DATABASE_TYPE} database...")

    if settings.DATABASE_TYPE == "postgresql":
        if not ensure_postgresql_database():
            sys.exit(1)

    print("Testing connection...")
    if not test_database_connection():
        print("Connection failed.")
        sys.exit(1)

    print("Running migrations...")
    command.upgrade(get_alembic_config(), "head")

    db_info = get_database_info()
    print(f"Done — {db_info['type']} ({db_info.get('version', '?')}), "
          f"{len(db_info['tables'])} tables")


def cmd_migrate() -> None:
    """Run pending migrations."""
    print("Running migrations...")
    command.upgrade(get_alembic_config(), "head")
    print("Done.")


def cmd_rollback() -> None:
    """Undo the most recent migration."""
    print("Rolling back one migration...")
    command.downgrade(get_alembic_config(), "-1")
    print("Done.")


def cmd_status() -> None:
    """Show current revision and history."""
    cfg = get_alembic_config()
    print("=== Current Revision ===")
    command.current(cfg, verbose=True)
    print("\n=== Migration History ===")
    command.history(cfg, verbose=True)


def cmd_generate(message: str) -> None:
    """Auto-generate a new migration from model changes."""
    print(f"Generating migration: {message}")
    command.revision(get_alembic_config(), message=message, autogenerate=True)
    print("Done — review the new file in migrations/versions/")


def cmd_stamp() -> None:
    """Stamp an existing database at head without running DDL.

    Use this when adopting Alembic on a database that was created
    with create_tables() and already has the current schema.
    """
    print("Stamping database at head...")
    command.stamp(get_alembic_config(), "head")
    print("Done — database is now tracked at the latest revision.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FinBot CTF Database Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("setup", help="Create database + run migrations")
    sub.add_parser("migrate", help="Run pending migrations")
    sub.add_parser("rollback", help="Undo the last migration")
    sub.add_parser("status", help="Show current revision and history")

    gen = sub.add_parser("generate", help="Auto-generate a migration from model changes")
    gen.add_argument("message", help="Short description of the change")

    sub.add_parser("stamp", help="Stamp existing database at head (no DDL)")

    args = parser.parse_args()

    commands = {
        "setup": cmd_setup,
        "migrate": cmd_migrate,
        "rollback": cmd_rollback,
        "status": cmd_status,
        "generate": lambda: cmd_generate(args.message),
        "stamp": cmd_stamp,
    }
    commands[args.command]()


if __name__ == "__main__":
    main()
