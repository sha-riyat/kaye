"""Async Postgres engine for Supabase.

Supabase's transaction pooler (port 6543) multiplexes connections, so server-side prepared
statements must be off, and we let the pooler do the pooling (NullPool): Modal containers are
short-lived and parallel.
"""

import asyncio
import sys
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession


def sqlalchemy_url(database_url: str) -> str:
    """Accept the plain `postgresql://` string Supabase shows and select the psycopg 3 driver."""
    for prefix in ("postgresql://", "postgres://"):
        if database_url.startswith(prefix):
            return "postgresql+psycopg://" + database_url.removeprefix(prefix)
    return database_url


def run[T](main: Coroutine[Any, Any, T]) -> T:
    """`asyncio.run` for scripts that use the database. Async psycopg cannot run on Windows' default
    Proactor loop, so local runs on Windows get a selector loop (Modal is Linux, unaffected)."""
    if sys.platform == "win32":
        return asyncio.run(main, loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(main)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        sqlalchemy_url(database_url),
        poolclass=NullPool,
        connect_args={"prepare_threshold": None},
    )


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine = make_engine(database_url)
        self._sessions = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session wrapped in a transaction: committed on success, rolled back on error."""
        async with self._sessions() as session, session.begin():
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
