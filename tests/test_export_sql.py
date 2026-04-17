# -*- coding: utf-8 -*-
"""Tests for lazy SQL parser helpers used by export editing."""

from types import SimpleNamespace

from app.ui import export_sql


def test_validate_sql_loads_sqlglot_lazily(monkeypatch) -> None:
    calls: list[str] = []
    fake_sqlglot = SimpleNamespace(
        ErrorLevel=SimpleNamespace(IMMEDIATE="immediate"),
        parse=lambda sql, dialect, error_level: [object()],
        transpile=lambda sql, read, write, pretty: ["SELECT 1"],
    )
    fake_errors = SimpleNamespace(ParseError=ValueError, TokenError=RuntimeError)

    def fake_import(name: str):
        calls.append(name)
        if name == "sqlglot":
            return fake_sqlglot
        if name == "sqlglot.errors":
            return fake_errors
        raise AssertionError(name)

    export_sql._load_sqlglot.cache_clear()
    monkeypatch.setattr(export_sql.importlib, "import_module", fake_import)

    ok, message = export_sql.validate_sql("SELECT 1")

    assert ok is True
    assert message == "SQL корректен"
    assert calls == ["sqlglot", "sqlglot.errors"]


def test_validate_sql_reports_missing_sqlglot(monkeypatch) -> None:
    export_sql._load_sqlglot.cache_clear()
    monkeypatch.setattr(
        export_sql.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing sqlglot")),
    )

    ok, message = export_sql.validate_sql("SELECT 1")

    assert ok is False
    assert message == "Парсер SQL недоступен"


def test_format_sql_returns_original_sql_when_sqlglot_unavailable(monkeypatch) -> None:
    export_sql._load_sqlglot.cache_clear()
    monkeypatch.setattr(
        export_sql.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("missing sqlglot")),
    )

    sql = "SELECT 1"

    assert export_sql.format_sql_for_tsql_editor(sql) == sql
