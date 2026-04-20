"""Tests for app.core.sql_client."""
import pytest

from app.config import AppConfig
from app.core import sql_client
from app.core.sql_client import SqlClient


class _FakeCursor:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []
        self.executed: list[tuple[str, tuple]] = []
        self.description = [("col1",), ("col2",)]
        self.fetchmany_calls: list[int] = []
        self._offset = 0

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def fetchall(self):
        # pyodbc.Cursor.fetchall returns list[Row] per its public contract;
        # keep the fake faithful so callers don't rely on accidental coercion.
        return list(self._rows)

    def fetchmany(self, size: int):
        self.fetchmany_calls.append(size)
        batch = self._rows[self._offset:self._offset + size]
        self._offset += len(batch)
        return list(batch)

    def __iter__(self):
        return iter(self._rows)


class _FakeConnection:
    def __init__(self, rows: list[tuple] | None = None) -> None:
        self._rows = rows or []
        self.closed = False
        self.cursor_calls = 0

    def cursor(self) -> _FakeCursor:
        self.cursor_calls += 1
        return _FakeCursor(self._rows)

    def close(self) -> None:
        self.closed = True


class _FakePyodbc:
    class Error(Exception):
        pass

    def __init__(self, connection: _FakeConnection | None = None) -> None:
        self.connection = connection or _FakeConnection()
        self.connect_calls: list[tuple[str, bool, int]] = []

    def connect(self, conn_str: str, autocommit: bool, timeout: int):
        self.connect_calls.append((conn_str, autocommit, timeout))
        return self.connection


def _cfg(**overrides: object) -> AppConfig:
    base = AppConfig(
        sql_instance="localhost",
        sql_database="master",
        sql_user="alice}",
        sql_password="pa;ss}",
        sql_trust_cert=False,
    )
    base.update(overrides)
    return base


def test_connect_escapes_connection_string_components(monkeypatch) -> None:
    fake_pyodbc = _FakePyodbc()
    monkeypatch.setattr(sql_client, "pyodbc", fake_pyodbc)
    monkeypatch.setattr(sql_client, "best_driver", lambda: "ODBC Driver 18 for SQL Server")

    client = SqlClient(_cfg(sql_instance="db;host}", sql_database="Sales;Archive"))
    client.connect()

    assert len(fake_pyodbc.connect_calls) == 1
    conn_str, autocommit, timeout = fake_pyodbc.connect_calls[0]
    assert autocommit is True
    assert timeout == 5
    assert "Driver={ODBC Driver 18 for SQL Server};" in conn_str
    assert "Server={db;host}}};" in conn_str
    assert "Database={Sales;Archive};" in conn_str
    assert "UID={alice}}};" in conn_str
    assert "PWD={pa;ss}}};" in conn_str
    assert "APP={iDentBridge};" in conn_str


def test_connect_wraps_driver_detection_failures(monkeypatch) -> None:
    fake_pyodbc = _FakePyodbc()
    monkeypatch.setattr(sql_client, "pyodbc", fake_pyodbc)
    monkeypatch.setattr(
        sql_client,
        "best_driver",
        lambda: (_ for _ in ()).throw(RuntimeError("pyodbc unavailable")),
    )

    client = SqlClient(_cfg())

    with pytest.raises(ConnectionError, match="pyodbc unavailable"):
        client.connect()


def test_connect_reports_missing_pyodbc(monkeypatch) -> None:
    monkeypatch.setattr(sql_client, "pyodbc", None)
    monkeypatch.setattr(sql_client, "_PYODBC_IMPORT_ERROR", ImportError("missing libodbc"))

    client = SqlClient(_cfg())

    with pytest.raises(ConnectionError, match="pyodbc is unavailable"):
        client.connect()


def test_query_materializes_rows_once(monkeypatch) -> None:
    fake_pyodbc = _FakePyodbc(_FakeConnection(rows=[(1, "alice"), (2, "bob")]))
    monkeypatch.setattr(sql_client, "pyodbc", fake_pyodbc)
    monkeypatch.setattr(sql_client, "best_driver", lambda: "ODBC Driver 18 for SQL Server")

    client = SqlClient(_cfg())
    client.connect()
    result = client.query("SELECT id, name FROM users WHERE active = ?", (1,))

    assert result.columns == ["col1", "col2"]
    assert result.rows == [(1, "alice"), (2, "bob")]
    assert result.count == 2
    assert result.truncated is False
    assert result.duration_ms >= 0
    assert result.duration_us >= 0


def test_query_respects_max_rows_and_marks_truncated(monkeypatch) -> None:
    fake_pyodbc = _FakePyodbc(
        _FakeConnection(rows=[(1, "alice"), (2, "bob"), (3, "carol")])
    )
    monkeypatch.setattr(sql_client, "pyodbc", fake_pyodbc)
    monkeypatch.setattr(sql_client, "best_driver", lambda: "ODBC Driver 18 for SQL Server")

    client = SqlClient(_cfg())
    client.connect()
    result = client.query("SELECT id, name FROM users", max_rows=2)

    assert result.rows == [(1, "alice"), (2, "bob")]
    assert result.count == 2
    assert result.truncated is True


def test_test_connection_returns_clear_failure_when_driver_detection_breaks(monkeypatch) -> None:
    fake_pyodbc = _FakePyodbc()
    monkeypatch.setattr(sql_client, "pyodbc", fake_pyodbc)
    monkeypatch.setattr(
        sql_client,
        "best_driver",
        lambda: (_ for _ in ()).throw(RuntimeError("no ODBC drivers")),
    )

    client = SqlClient(_cfg())
    ok, msg = client.test_connection()

    assert ok is False
    assert "no ODBC drivers" in msg


def test_test_connection_formats_duration_compact(monkeypatch) -> None:
    class _FakeClient(SqlClient):
        def connect(self) -> None:
            return None

        def is_alive(self) -> bool:
            return True

        def query(self, sql: str, params: tuple = (), *, max_rows: int | None = None):
            return sql_client.QueryResult(
                columns=["count"],
                rows=[(17,)],
                count=1,
                duration_ms=12,
                duration_us=12_345,
            )

        def disconnect(self) -> None:
            return None

    client = _FakeClient(_cfg())

    ok, msg = client.test_connection()

    assert ok is True
    assert msg == "Подключено · 17 таблиц · 12.3 мс"
