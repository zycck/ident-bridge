# -*- coding: utf-8 -*-
"""Single source of truth for SQL Server ODBC connection strings."""

from app.core.constants import APP_NAME


def _odbc_escape(value: str) -> str:
    """Wrap an ODBC value in braces and escape closing braces inside it."""
    return "{" + value.replace("}", "}}") + "}"


def build_sql_connection_string(
    *,
    driver: str,
    server: str,
    database: str = "",
    user: str = "",
    password: str = "",
    trust_cert: bool = True,
    timeout: int = 5,
) -> str:
    """
    Build an ODBC connection string for MS SQL Server.

    If `user` is empty, falls back to Windows Trusted Connection.
    `trust_cert=True` accepts self-signed/untrusted server certs (common in
    LAN deployments). `timeout` is the TCP connect timeout in seconds.
    """
    auth = (
        f"UID={_odbc_escape(user)};PWD={_odbc_escape(password)};"
        if user
        else "Trusted_Connection=yes;"
    )
    db = f"Database={_odbc_escape(database)};" if database else ""
    return (
        f"Driver={_odbc_escape(driver)};"
        f"Server={_odbc_escape(server)};"
        f"{db}"
        f"{auth}"
        f"APP={_odbc_escape(APP_NAME)};"
        f"TrustServerCertificate={'yes' if trust_cert else 'no'};"
        f"Connect Timeout={timeout};"
    )
