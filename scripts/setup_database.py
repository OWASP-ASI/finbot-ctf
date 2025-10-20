"""
Setup the database for the FinBot platform
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from finbot.config import settings

# Import models to register them with the declarative base
from finbot.core.data.database import (
    create_tables,
    get_database_info,
    test_database_connection,
)


def setup_postgresql() -> bool:
    """Setup the PostgreSQL database"""

    print("Setting up PostgreSQL database...")

    try:
        # pylint: disable=import-outside-toplevel
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

        # connect to PostgreSQL
        conn = psycopg2.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database="postgres",  # connect to default to figure things out.
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        cursor = conn.cursor()

        # create db if it doesn't exist
        cursor.execute(
            f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{settings.POSTGRES_DB}'"
        )
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(f"CREATE DATABASE {settings.POSTGRES_DB}")
            print(f"Database {settings.POSTGRES_DB} created successfully")
        else:
            print(f"Database {settings.POSTGRES_DB} already exists")

        cursor.close()
        conn.close()
        return True
    except ImportError:
        print("psycopg2 is not installed")
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"Error setting up PostgreSQL database: {e}")
        return False


def setup_sqlite() -> bool:
    """Setup the SQLite database"""

    print("📁 Setting up SQLite database...")

    try:
        db_path = settings.get_database_url().replace("sqlite:///", "")
        db_dir = os.path.dirname(db_path)

        # Create directory if needed
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"📁 Created directory: {db_dir}")

        print(f"📄 SQLite database will be created at: {db_path}")
        return True

    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ SQLite setup failed: {e}")
        return False


def main() -> None:
    """DB Setup Script"""
    print("🚀 FinBot CTF Database Setup")
    print(f"Database Type: {settings.DATABASE_TYPE}")
    print(f"Database URL: {settings.get_database_url()}")
    print()

    # DB specific setup
    if settings.DATABASE_TYPE == "sqlite":
        if not setup_sqlite():
            sys.exit(1)
    elif settings.DATABASE_TYPE == "postgresql":
        if not setup_postgresql():
            sys.exit(1)
    else:
        print(f"Unsupported database type: {settings.DATABASE_TYPE}")
        sys.exit(1)

    # Test Connection
    print("Testing database connection...")
    if not test_database_connection():
        sys.exit(1)

    # Create Tables
    print("Creating database tables...")
    try:
        create_tables()
    except Exception as e:  # pylint: disable=broad-exception-caught
        print(f"❌ Error creating database tables: {e}")
        sys.exit(1)

    # Verification
    print("Verifying database setup...")
    db_info = get_database_info()

    print("✅ Database setup complete")
    print(f"Database: {db_info['type']} ({db_info.get('version', 'Unknown version')})")
    print(f"Tables created: {len(db_info['tables'])}")
    print(f"Tables: {', '.join(db_info['tables'])}")


if __name__ == "__main__":
    main()
