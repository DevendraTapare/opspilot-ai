"""Official PostgreSQL saver and session-scoped cross-process resume exclusion."""

import asyncio
import hashlib
import re
import sys
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import AsyncConnection
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from opspilot.durable.contracts import ExecutionError


def lock_key(value):
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)


def run_async(coroutine):
    # Psycopg async does not support Windows' default ProactorEventLoop.
    factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    return asyncio.run(coroutine, loop_factory=factory)


class PostgreSQLPersistence:
    def __init__(self, engine, checkpoint_schema="opspilot_checkpoints"):
        if engine.dialect.name != "postgresql" or not re.fullmatch(
            r"opspilot_checkpoints|opspilot_test_[0-9a-f]{32}", checkpoint_schema
        ):
            raise ValueError("durable execution requires dedicated PostgreSQL checkpoint storage")
        url = engine.url
        if url.host not in {"127.0.0.1", "localhost", "db", "test-db"}:
            raise ValueError("durable execution is restricted to the local simulator")
        with engine.connect() as connection:
            self.data_schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
        if self.data_schema != "public" and not re.fullmatch(
            r"opspilot_test_[0-9a-f]{32}", self.data_schema
        ):
            raise ValueError("unexpected data schema")
        values = {
            "host": url.host,
            "port": url.port or 5432,
            "dbname": url.database,
            "user": url.username,
            "password": url.password or "",
            "connect_timeout": 5,
        }
        self.checkpoint_conninfo = make_conninfo(
            **values, options=f"-csearch_path={checkpoint_schema}"
        )
        self.lock_conninfo = make_conninfo(**values, options=f"-csearch_path={self.data_schema}")
        self.namespace = f"{url.database}:{self.data_schema}"

    @asynccontextmanager
    async def saver(self):
        async with await AsyncConnection.connect(
            self.checkpoint_conninfo, autocommit=True, row_factory=dict_row, prepare_threshold=0
        ) as conn:
            setup_key = lock_key(self.namespace + ":checkpoint-setup")
            await conn.execute("SELECT pg_advisory_lock(%s)", (setup_key,))
            saver = AsyncPostgresSaver(
                conn, serde=JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)
            )
            try:
                await saver.setup()
            finally:
                await conn.execute("SELECT pg_advisory_unlock(%s)", (setup_key,))
            yield saver

    @asynccontextmanager
    async def run_lock(self, run_id):
        async with await AsyncConnection.connect(self.lock_conninfo, autocommit=True) as conn:
            key = lock_key(self.namespace + ":run:" + run_id)
            cursor = await conn.execute("SELECT pg_try_advisory_lock(%s)", (key,))
            if not (await cursor.fetchone())[0]:
                raise ExecutionError("RUN_BUSY")
            try:
                yield conn
            finally:
                if not conn.closed:
                    await conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
