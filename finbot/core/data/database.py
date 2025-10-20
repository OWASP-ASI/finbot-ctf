"""
DB Configuration and Management
"""

import logging
import os
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from finbot.config import settings

# Setup logging
logger = logging.getLogger(__name__)


def create_database_engine():
    """Create a database engine based on the configuration"""

    database_url = settings.get_database_url()
    config = settings.get_database_config()

    logger.info("Configuring %s database", settings.DATABASE_TYPE.upper())
    logger.info(
        "Database URL: %s",
        f"{database_url.split('@')[0]}@***" if "@" in database_url else database_url,
    )

    db_engine = create_engine(database_url, **config)

    # SQLite specific configuration for performance
    if settings.DATABASE_TYPE == "sqlite":

        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            _ = connection_record
            if "sqlite" in str(dbapi_connection):
                cursor = dbapi_connection.cursor()
                # enable foreign key constraints
                cursor.execute("PRAGMA foreign_keys=ON")
                # better concurrency and performance
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA cache_size=10000")
                cursor.execute("PRAGMA temp_store=MEMORY")
                cursor.close()

    logger.info("Database engine created successfully")
    return db_engine


# db engine instance
engine = create_database_engine()

# session factory
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# Declarative base for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Get a database session
    - Ensures proper session handling and cleanup
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error("Database session error: %s", e)
        db.rollback()
        raise
    finally:
        db.close()
        logger.info("Database session closed")


def create_tables() -> None:
    """Create all tables in the database
    - This is called during application startup
    """
    try:
        logger.info("Creating all database tables")
        # for sqlite, ensure db exists
        if settings.DATABASE_TYPE == "sqlite":
            db_path = settings.get_database_url().replace("sqlite:///", "")
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info("Created directory for SQLite database: %s", db_dir)
        # create all tables
        Base.metadata.create_all(bind=engine)

        # Verify all tables are created
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if not tables:
            logger.error("No tables found in the database")
            raise Exception("No tables found in the database")  # pylint: disable=broad-exception-raised
        logger.info("All database tables created successfully: %s", tables)
    except Exception as e:
        logger.error("Error creating database tables: %s", e)
        raise


def test_database_connection() -> bool:
    """Test the database connection Return True if successful, False otherwise"""
    try:
        with engine.connect() as connection:
            result = None
            if settings.DATABASE_TYPE == "sqlite":
                result = connection.execute(text("SELECT 1")).fetchone()
            elif settings.DATABASE_TYPE == "postgresql":
                result = connection.execute(text("SELECT version()")).fetchone()
            logger.info("Database connection test result: %s", result)
            return result is not None and result[0] == 1
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error testing database connection: %s", e)
        return False


def get_database_info() -> dict:
    """Get database information for health checks etc."""
    try:
        with engine.connect() as connection:
            info = {
                "type": settings.DATABASE_TYPE,
                "url": settings.get_database_url().split("@")[0] + "@***"
                if "@" in settings.get_database_url()
                else settings.get_database_url(),
                "tables": list(Base.metadata.tables.keys()),
                "connected": True,
            }
            if settings.DATABASE_TYPE == "sqlite":
                result = connection.execute(text("SELECT sqlite_version()")).fetchone()
                info["version"] = f"SQLite {result[0]}" if result else "Unknown"
            elif settings.DATABASE_TYPE == "postgresql":
                result = connection.execute(text("SELECT version()")).fetchone()
                info["version"] = f"PostgreSQL {result[0]}" if result else "Unknown"
            return info
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error getting database information: %s", e)
        return {
            "type": settings.DATABASE_TYPE,
            "url": settings.get_database_url().split("@")[0] + "@***"
            if "@" in settings.get_database_url()
            else settings.get_database_url(),
            "tables": [],
            "connected": False,
            "error": str(e),
        }


def reset_database() -> None:
    """Reset the database
    WARNING: This will drop all tables and data in the database
    """
    if not settings.DEBUG:
        raise RuntimeError("🚨 Resetting the database is only allowed in debug mode")
    logger.warning("🚨 Resetting the database - ALL DATA WILL BE LOST")
    try:
        # drop all tables
        Base.metadata.drop_all(bind=engine)
        logger.info("All tables dropped successfully")

        # recreate all tables
        create_tables()
        logger.info("Database reset completed successfully")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error resetting database: %s", e)
        raise
