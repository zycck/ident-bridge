# -*- coding: utf-8 -*-
"""Tests for app.core.connection."""
from app.core.connection import _odbc_escape, build_sql_connection_string


def test_odbc_escape_wraps_and_doubles_closing_braces() -> None:
    assert _odbc_escape("name}") == "{name}}}"


def test_build_sql_connection_string_escapes_all_unsafe_values() -> None:
    conn_str = build_sql_connection_string(
        driver="ODBC Driver 18 for SQL Server",
        server="db;host}",
        database="Sales;Archive",
        user="alice}",
        password="pa;ss}",
        trust_cert=False,
        timeout=7,
    )

    assert conn_str == (
        "Driver={ODBC Driver 18 for SQL Server};"
        "Server={db;host}}};"
        "Database={Sales;Archive};"
        "UID={alice}}};"
        "PWD={pa;ss}}};"
        "APP={iDentBridge};"
        "TrustServerCertificate=no;"
        "Connect Timeout=7;"
    )


def test_build_sql_connection_string_uses_trusted_connection_without_user() -> None:
    conn_str = build_sql_connection_string(
        driver="ODBC Driver 18 for SQL Server",
        server="localhost",
        trust_cert=True,
    )

    assert "Trusted_Connection=yes;" in conn_str
    assert "UID=" not in conn_str
    assert "PWD=" not in conn_str
