import time
import random
from datetime import datetime, timezone

import pyodbc

from app.config import AppConfig, QueryResult

_MAX_ATTEMPTS = 3
_BASE_DELAY = 2.0   # seconds; doubles each retry
_JITTER = 0.10      # ±10 %


class SqlClient:
    """pyodbc-based SQL Server client. NOT thread-safe — one instance per thread."""

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._conn: pyodbc.Connection | None = None

    def connect(self) -> None:
        last_exc: Exception | None = None
        delay = _BASE_DELAY

        for attempt in range(_MAX_ATTEMPTS):
            if attempt:
                jitter = delay * _JITTER * (2 * random.random() - 1)
                time.sleep(delay + jitter)
                delay *= 2

            try:
                conn_str = (
                    "Driver={ODBC Driver 17 for SQL Server};"
                    f"Server={self._cfg['sql_instance']};"
                    f"Database={self._cfg['sql_database']};"
                    f"UID={self._cfg['sql_user']};"
                    f"PWD={self._cfg['sql_password']};"
                    "APP=iDentBridge"
                )
                self._conn = pyodbc.connect(conn_str, autocommit=True, timeout=10)
                # Python strings are immutable; we cannot truly zero conn_str in memory.
                # Credentials are protected at rest via DPAPI in config.json.
                return

            except pyodbc.Error as exc:
                last_exc = exc

        sqlstate = last_exc.args[0] if (last_exc and last_exc.args) else "unknown"
        raise ConnectionError(
            f"SQL Server connection failed after {_MAX_ATTEMPTS} attempts "
            f"(SQLSTATE {sqlstate})"
        ) from None

    def disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except pyodbc.Error:
                pass
            finally:
                self._conn = None

    def is_alive(self) -> bool:
        if self._conn is None:
            return False
        try:
            self._conn.cursor().execute("SELECT 1")
            return True
        except pyodbc.Error:
            return False

    def query(self, sql: str, params: tuple = ()) -> QueryResult:
        start = datetime.now(timezone.utc)
        cursor = self._conn.cursor()  # type: ignore[union-attr]
        cursor.execute(sql, params)
        columns = [d[0] for d in cursor.description]
        rows = list(cursor.fetchall())
        elapsed = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        return QueryResult(
            columns=columns,
            rows=rows,
            count=len(rows),
            duration_ms=elapsed,
        )

    def test_connection(self) -> tuple[bool, str]:
        try:
            self.connect()
            alive = self.is_alive()
            return (alive, '' if alive else 'Connection established but health-check failed')
        except Exception as exc:
            # Return sanitized message — never expose raw pyodbc error (may contain DSN)
            return (False, str(exc))
        finally:
            self.disconnect()
