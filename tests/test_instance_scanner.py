# -*- coding: utf-8 -*-
"""Tests for app.core.instance_scanner."""
import pytest

from app.config import SqlInstance
from app.core import instance_scanner


class _FakePyodbc:
    class Error(Exception):
        pass

    def __init__(self, rows: list[tuple[str]] | None = None) -> None:
        self.rows = rows or []
        self.connect_calls: list[tuple[str, bool, int]] = []

    def connect(self, conn_str: str, autocommit: bool, timeout: int):
        self.connect_calls.append((conn_str, autocommit, timeout))
        return _FakeConnection(self.rows)


class _FakeCursor:
    def __init__(self, rows: list[tuple[str]]):
        self._rows = rows
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))

    def __iter__(self):
        return iter(self._rows)


class _FakeConnection:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self._rows = rows
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    def close(self) -> None:
        self.closed = True


def test_scan_local_returns_empty_when_winreg_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(instance_scanner, "winreg", None)

    assert instance_scanner.scan_local() == []


def test_scan_network_returns_empty_on_nonzero_exit_without_output(monkeypatch) -> None:
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "sqlcmd: command not found"

    monkeypatch.setattr(instance_scanner.subprocess, "run", lambda *a, **k: _Result())

    assert instance_scanner.scan_network() == []


def test_scan_network_parses_instances(monkeypatch) -> None:
    class _Result:
        returncode = 0
        stdout = "Servers:\nlocalhost\\SQLEXPRESS\nSERVERONLY\n"
        stderr = ""

    monkeypatch.setattr(instance_scanner.subprocess, "run", lambda *a, **k: _Result())

    instances = instance_scanner.scan_network()

    assert instances == [
        SqlInstance(name="SQLEXPRESS", host="localhost", display="localhost\\SQLEXPRESS"),
        SqlInstance(name="", host="SERVERONLY", display="SERVERONLY"),
    ]


def test_scan_all_deduplicates_and_sorts(monkeypatch) -> None:
    monkeypatch.setattr(
        instance_scanner,
        "scan_local",
        lambda: [
            SqlInstance(name="B", host="localhost", display="localhost\\B"),
            SqlInstance(name="A", host="localhost", display="localhost\\A"),
        ],
    )
    monkeypatch.setattr(
        instance_scanner,
        "scan_network",
        lambda: [
            SqlInstance(name="b", host="localhost", display="localhost\\B"),
            SqlInstance(name="C", host="server", display="server\\C"),
        ],
    )

    displays = [item.display for item in instance_scanner.scan_all()]
    assert displays == ["localhost\\A", "localhost\\B", "server\\C"]


def test_list_databases_requires_pyodbc(monkeypatch) -> None:
    monkeypatch.setattr(instance_scanner, "pyodbc", None)
    monkeypatch.setattr(
        instance_scanner,
        "_PYODBC_IMPORT_ERROR",
        ImportError("libodbc.so.2 missing"),
    )

    with pytest.raises(RuntimeError, match="pyodbc is unavailable"):
        instance_scanner.list_databases(
            SqlInstance(name="X", host="localhost", display="localhost\\X"),
            "",
            "",
        )


def test_list_databases_iterates_rows(monkeypatch) -> None:
    fake_pyodbc = _FakePyodbc(rows=[("db1",), ("db2",)])
    monkeypatch.setattr(instance_scanner, "pyodbc", fake_pyodbc)
    monkeypatch.setattr(instance_scanner, "best_driver", lambda: "ODBC Driver 18 for SQL Server")
    monkeypatch.setattr(instance_scanner, "build_sql_connection_string", lambda **kwargs: "dsn")

    databases = instance_scanner.list_databases(
        SqlInstance(name="X", host="localhost", display="localhost\\X"),
        "user",
        "password",
    )

    assert databases == ["db1", "db2"]
    assert fake_pyodbc.connect_calls == [("dsn", True, 3)]
