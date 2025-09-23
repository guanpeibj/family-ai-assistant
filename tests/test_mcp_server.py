import uuid
from unittest.mock import AsyncMock

import pytest

from mcp_server.generic_mcp_server import GenericMCPServer
from importlib import import_module
from types import ModuleType
from unittest.mock import patch


class _DummyConnection:
    def __init__(self):
        self.last_sql = None
        self.last_params = None
        self.fetchval_return = 10

    async def fetch(self, sql, *params):
        self.last_sql = sql
        self.last_params = params
        return []

    async def fetchval(self, sql, *params):
        self.last_sql = sql
        self.last_params = params
        return self.fetchval_return


class _AcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _AcquireCtx(self._conn)


@pytest.mark.asyncio
async def test_aggregate_family_scope_uses_any_and_multiple_ids():
    server = GenericMCPServer()
    conn = _DummyConnection()
    server.pool = _DummyPool(conn)
    server._ensure_user = AsyncMock()

    result = await server._aggregate(
        ["user_a", "user_b"],
        operation="sum",
        field="amount",
        filters={"jsonb_equals": {"type": "expense"}},
    )

    assert conn.last_sql.startswith(
        "SELECT SUM(amount) as result FROM memories WHERE user_id = ANY($1::uuid[])"
    )
    assert isinstance(conn.last_params[0], list)
    assert len(conn.last_params[0]) == 2
    for raw in ["user_a", "user_b"]:
        normalized = uuid.uuid5(uuid.NAMESPACE_URL, f"faa:{raw}")
        assert normalized in conn.last_params[0]

    assert server._ensure_user.await_count == 2
    assert result["operation"] == "sum"
    assert result["result"] == float(conn.fetchval_return)


def _run_upgrade(module: ModuleType):
    executed = []

    def _capture(stmt):
        executed.append(stmt)

    with patch.object(module.op, "execute", side_effect=_capture):
        module.upgrade()
    return executed


def test_generated_columns_migration_creates_expected_columns():
    module = import_module("alembic.versions.20250314_add_generated_columns")
    executed = _run_upgrade(module)

    expected_columns = [
        "thread_id_extracted",
        "type_extracted",
        "category_extracted",
        "person_extracted",
        "metric_extracted",
        "subject_extracted",
        "source_extracted",
        "value_extracted",
    ]

    for column in expected_columns:
        assert any(column in stmt for stmt in executed), f"missing column {column}"
