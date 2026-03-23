"""Alembic migration environment configuration."""

# pylint: disable=no-member

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from finbot.config import settings
from finbot.core.data.database import Base

# Register ALL model modules so Base.metadata knows every table.
from finbot.apps.cc import models as _cc_models  # noqa: F401
from finbot.core.analytics import models as _analytics_models  # noqa: F401
from finbot.core.data import models as _core_models  # noqa: F401
from finbot.mcp.servers.findrive import models as _findrive_models  # noqa: F401
from finbot.mcp.servers.finmail import models as _finmail_models  # noqa: F401
from finbot.mcp.servers.finstripe import models as _finstripe_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return settings.get_database_url()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connect to the database)."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
