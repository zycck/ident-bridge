"""Factory for :class:`~app.database.protocol.DatabaseClient` instances.

Single place that maps a backend name (``"mssql"``) to a concrete class.
Call sites ask for what they want by kind, not by import, so we can add
``"postgresql"`` / ``"sqlite"`` / whatever without touching the UI or
the export pipeline.

Current backends: ``mssql`` → :class:`app.core.sql_client.SqlClient`
(pyodbc-backed, moves to ``app.database.mssql.client`` in Stage 5 of
the audit plan).
"""

from collections.abc import Callable

from app.config import AppConfig
from app.database.protocol import DatabaseClient

# Kept as a lazy import table so the package can be imported on systems
# that don't have pyodbc — the error only fires when the caller actually
# asks for the MSSQL backend.


def _load_mssql() -> type:
    from app.core.sql_client import SqlClient
    return SqlClient


_REGISTRY: dict[str, Callable[[], type]] = {
    "mssql": _load_mssql,
}


def supported_kinds() -> tuple[str, ...]:
    """Sorted tuple of backend names this build can produce clients for."""
    return tuple(sorted(_REGISTRY))


def create_database_client(kind: str, cfg: AppConfig) -> DatabaseClient:
    """Return a new client of the requested backend.

    >>> create_database_client("mssql", cfg)            # doctest: +SKIP
    <SqlClient ...>

    Raises :class:`ValueError` if ``kind`` is not registered; the caller
    can surface the list via :func:`supported_kinds` in the error message.
    """
    loader = _REGISTRY.get(kind.lower())
    if loader is None:
        raise ValueError(
            f"Unknown database backend {kind!r}. "
            f"Known backends: {', '.join(supported_kinds()) or '(none)'}"
        )
    cls = loader()
    return cls(cfg)


__all__ = ["create_database_client", "supported_kinds"]
