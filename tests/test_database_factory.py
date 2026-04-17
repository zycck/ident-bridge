"""Tests for app.database.protocol + app.database.factory."""

from __future__ import annotations

import pytest

from app.config import AppConfig, QueryResult
from app.database import (
    DatabaseClient,
    create_database_client,
    supported_kinds,
)
from app.database.factory import _REGISTRY


def test_supported_kinds_lists_mssql():
    assert "mssql" in supported_kinds()


def test_create_mssql_returns_database_client_compatible():
    cfg = AppConfig(sql_instance="localhost")
    client = create_database_client("mssql", cfg)
    assert isinstance(client, DatabaseClient)


def test_create_is_case_insensitive():
    cfg = AppConfig(sql_instance="localhost")
    a = create_database_client("mssql", cfg)
    b = create_database_client("MSSQL", cfg)
    assert type(a) is type(b)


def test_unknown_kind_raises_valueerror():
    with pytest.raises(ValueError, match="mongodb"):
        create_database_client("mongodb", AppConfig())


def test_unknown_kind_lists_known_backends():
    with pytest.raises(ValueError) as excinfo:
        create_database_client("oracle", AppConfig())
    assert "mssql" in str(excinfo.value)


def test_sqlclient_conforms_to_protocol_at_runtime():
    """SqlClient should satisfy the structural DatabaseClient contract."""
    from app.core.sql_client import SqlClient
    assert issubclass(SqlClient, DatabaseClient)


def test_factory_registry_is_extendable(monkeypatch):
    """Downstream code can register new backends at runtime."""
    class _FakeClient:
        def __init__(self, cfg): self.cfg = cfg
        def connect(self): pass
        def disconnect(self): pass
        def is_alive(self): return True
        def query(self, sql, params=()): return QueryResult([], [], 0, 0)
        def test_connection(self): return True, ""

    monkeypatch.setitem(_REGISTRY, "fake", lambda: _FakeClient)
    client = create_database_client("fake", AppConfig())
    assert isinstance(client, _FakeClient)
    assert isinstance(client, DatabaseClient)
