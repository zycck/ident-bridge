"""Database client protocol + factory.

Concrete implementations (currently only MSSQL via pyodbc) live in
subpackages. Adding PostgreSQL, SQLite, or any other backend is a new
subpackage + one line in :mod:`app.database.factory`.
"""

from __future__ import annotations

from app.database.factory import create_database_client, supported_kinds
from app.database.protocol import DatabaseClient

__all__ = ["DatabaseClient", "create_database_client", "supported_kinds"]
