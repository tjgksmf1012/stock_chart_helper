from __future__ import annotations

import ssl
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

settings = get_settings()

def _ssl_connect_args_for_mode(sslmode: str) -> dict[str, Any]:
    mode = sslmode.strip().lower()
    if mode in {"disable", "allow", "prefer"}:
        return {}

    context = ssl.create_default_context()
    if mode == "require":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif mode == "verify-ca":
        context.check_hostname = False

    return {"ssl": context}


def normalize_database_url(database_url: str) -> tuple[str, dict[str, Any]]:
    url = make_url(database_url)
    if url.drivername != "postgresql+asyncpg":
        return database_url, {}

    connect_args: dict[str, Any] = {}
    removals: list[str] = []

    sslmode = url.query.get("sslmode")
    if sslmode:
        removals.append("sslmode")
        connect_args.update(_ssl_connect_args_for_mode(sslmode))

    if "channel_binding" in url.query:
        removals.append("channel_binding")

    normalized_url = url.difference_update_query(removals) if removals else url
    return normalized_url.render_as_string(hide_password=False), connect_args


def _create_engine():
    database_url, connect_args = normalize_database_url(settings.database_url)
    engine_kwargs: dict[str, Any] = {
        "echo": settings.debug,
        "pool_pre_ping": True,
    }
    if connect_args:
        engine_kwargs["connect_args"] = connect_args
    return create_async_engine(database_url, **engine_kwargs)


engine = _create_engine()
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    from .. import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_run_runtime_migrations)


def _run_runtime_migrations(sync_conn) -> None:
    inspector = inspect(sync_conn)
    tables = set(inspector.get_table_names())
    if "signal_outcomes" not in tables:
        return

    columns = {column["name"] for column in inspector.get_columns("signal_outcomes")}
    if "intent" not in columns:
        sync_conn.execute(text("ALTER TABLE signal_outcomes ADD COLUMN intent VARCHAR(40)"))
        sync_conn.execute(text("UPDATE signal_outcomes SET intent = 'breakout_wait' WHERE intent IS NULL"))
    if "evaluation_basis" not in columns:
        sync_conn.execute(text("ALTER TABLE signal_outcomes ADD COLUMN evaluation_basis VARCHAR(40)"))
    if "observed_high" not in columns:
        sync_conn.execute(text("ALTER TABLE signal_outcomes ADD COLUMN observed_high DOUBLE PRECISION"))
    if "observed_low" not in columns:
        sync_conn.execute(text("ALTER TABLE signal_outcomes ADD COLUMN observed_low DOUBLE PRECISION"))
