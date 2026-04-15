import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models so Alembic can detect changes
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import settings
from app.db.base import Base  # noqa: F401 — imports all models via __all__

config = context.config
fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Which database to migrate — set via -x flag:
#   alembic -x db=meta upgrade head
#   alembic -x db=features upgrade head
_db_target = context.get_x_argument(as_dictionary=True).get("db", "meta")

if _db_target == "features":
    _url = settings.features_shard_0_url
else:
    _url = settings.meta_db_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _url
    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
