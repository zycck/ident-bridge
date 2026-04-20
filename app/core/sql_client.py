import random
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, final

try:
    import pyodbc
except Exception as exc:  # pragma: no cover - runtime availability differs by OS
    pyodbc = None
    _PYODBC_IMPORT_ERROR = exc
else:
    _PYODBC_IMPORT_ERROR = None

from app.config import AppConfig, QueryResult
from app.core.connection import build_sql_connection_string
from app.core.formatters import format_duration_compact
from app.core.odbc_utils import best_driver

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyodbc as _pyodbc

_MAX_ATTEMPTS = 3
_BASE_DELAY = 2.0   # seconds; doubles each retry
_JITTER = 0.10      # ±10 %


@final
class SqlClient:
    """pyodbc-based SQL Server client. NOT thread-safe — one instance per thread."""

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._conn: object | None = None

    def _require_pyodbc(self) -> None:
        if pyodbc is None:
            raise ConnectionError(
                "pyodbc is unavailable; install pyodbc and the native ODBC runtime"
            ) from _PYODBC_IMPORT_ERROR

    def connect(self) -> None:
        """Open a live SQL Server connection with bounded retries."""
        self._require_pyodbc()
        instance = self._cfg.get("sql_instance") or ""
        database = self._cfg.get("sql_database") or ""
        if not instance:
            raise ConnectionError("SQL Server instance not configured")

        last_exc: Exception | None = None
        delay = _BASE_DELAY

        for attempt in range(_MAX_ATTEMPTS):
            if attempt:
                jitter = delay * _JITTER * (2 * random.random() - 1)
                time.sleep(delay + jitter)
                delay *= 2

            try:
                driver = best_driver()
                user = self._cfg.get("sql_user", "") or ""
                password = self._cfg.get("sql_password", "") or ""
                conn_str = build_sql_connection_string(
                    driver=driver,
                    server=instance,
                    database=database,
                    user=user,
                    password=password,
                    trust_cert=self._cfg.get("sql_trust_cert", True),
                    timeout=5,
                )
                self._conn = pyodbc.connect(conn_str, autocommit=True, timeout=5)
                # Python strings are immutable; we cannot truly zero conn_str in memory.
                # Credentials are protected at rest via DPAPI in config.json.
                return

            except RuntimeError as exc:
                last_exc = exc
                break
            except pyodbc.Error as exc:
                last_exc = exc

        sqlstate = last_exc.args[0] if (last_exc and last_exc.args) else "unknown"
        raise ConnectionError(
            f"SQL Server connection failed after {_MAX_ATTEMPTS} attempts "
            f"(SQLSTATE {sqlstate})"
        ) from last_exc

    def disconnect(self) -> None:
        """Close the current connection if one is open."""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as exc:
                if pyodbc is not None and isinstance(exc, pyodbc.Error):
                    pass
                else:
                    raise
            finally:
                self._conn = None

    def is_alive(self) -> bool:
        """Return ``True`` when the current connection responds to ``SELECT 1``."""
        if self._conn is None:
            return False
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception as exc:
            if pyodbc is not None and isinstance(exc, pyodbc.Error):
                return False
            raise

    def query(self, sql: str, params: tuple = (), *, max_rows: int | None = None) -> QueryResult:
        """Execute one SQL statement and materialize the result rows."""
        if self._conn is None:
            raise RuntimeError("Not connected")
        started_ns = time.perf_counter_ns()
        with self._conn.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [d[0] for d in cursor.description]
            truncated = False
            if max_rows is None:
                # pyodbc.Cursor.fetchall() contractually returns list[Row];
                # no defensive coercion needed.
                rows = cursor.fetchall()
            else:
                rows = []
                fetchmany = getattr(cursor, "fetchmany", None)
                if callable(fetchmany):
                    batch_size = max(1, min(max_rows, 500))
                    while len(rows) < max_rows:
                        batch = fetchmany(batch_size)
                        if not batch:
                            break
                        rows.extend(batch[: max_rows - len(rows)])
                        if len(batch) == batch_size and len(rows) >= max_rows:
                            extra = fetchmany(1)
                            if extra:
                                truncated = True
                            break
                    else:
                        truncated = True
                else:
                    all_rows = cursor.fetchall()
                    if not isinstance(all_rows, list):
                        all_rows = list(all_rows)
                    truncated = len(all_rows) > max_rows
                    rows = all_rows[:max_rows]
        elapsed_us = max(0, (time.perf_counter_ns() - started_ns) // 1_000)
        return QueryResult(
            columns=columns,
            rows=rows,
            count=len(rows),
            duration_ms=elapsed_us // 1_000,
            duration_us=elapsed_us,
            truncated=truncated,
        )

    def test_connection(self) -> tuple[bool, str]:
        """Connect, run a cheap probe query, and return a user-facing status."""
        try:
            self.connect()
            if not self.is_alive():
                return (False, 'Подключение установлено, но проверка связи не прошла')
            result = self.query(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES"
                " WHERE TABLE_TYPE = 'BASE TABLE'"
            )
            table_count = result.rows[0][0] if result.rows else 0
            return (
                True,
                f"Подключено · {table_count} таблиц · "
                f"{format_duration_compact(result.duration_us)}",
            )
        except ConnectionError as exc:
            # ConnectionError already contains a sanitized message (no DSN)
            return (False, str(exc))
        except Exception:
            return (False, "Неожиданная ошибка при подключении")
        finally:
            self.disconnect()
