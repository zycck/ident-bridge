# -*- coding: utf-8 -*-
"""Single source of truth for SQL Server ODBC connection strings."""
from __future__ import annotations


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
    auth = f"UID={user};PWD={password};" if user else "Trusted_Connection=yes;"
    db   = f"Database={database};" if database else ""
    return (
        f"Driver={{{driver}}};"
        f"Server={server};"
        f"{db}"
        f"{auth}"
        f"APP=iDentBridge;"
        f"TrustServerCertificate={'yes' if trust_cert else 'no'};"
        f"Connect Timeout={timeout};"
    )
