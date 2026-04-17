"""Protocol contract every database client must satisfy.

The contract is intentionally minimal — it describes exactly what the
rest of the app already uses. Adding methods later means updating this
file and every implementation at the same time; that's the correct
friction level for an extension point we want to keep small.

runtime_checkable lets tests assert conformance via ``isinstance`` so
structural breakage is caught on import, not when a real DB connects.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.config import AppConfig, QueryResult


@runtime_checkable
class DatabaseClient(Protocol):
    """One stateful DB session.

    Lifecycle: ``__init__(cfg) → connect() → query() [× n] → disconnect()``.

    Implementations are not expected to be thread-safe; callers create
    one client per thread. See :class:`app.core.sql_client.SqlClient` for
    the MSSQL implementation.
    """

    def __init__(self, cfg: AppConfig) -> None: ...

    def connect(self) -> None:
        """Establish a live session. Raise :class:`ConnectionError` on failure."""
        ...

    def disconnect(self) -> None:
        """Release the session. Safe to call when never connected."""
        ...

    def is_alive(self) -> bool:
        """Cheap health check (``SELECT 1``)."""
        ...

    def query(self, sql: str, params: tuple = ()) -> QueryResult:
        """Execute one SQL statement, return the full result."""
        ...

    def test_connection(self) -> tuple[bool, str]:
        """Connect, ping, disconnect. Return ``(ok, human_message)``."""
        ...


__all__ = ["DatabaseClient"]
