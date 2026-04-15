import time
import random
from datetime import datetime, timezone

import pyodbc

from app.config import AppConfig, QueryResult
from app.core.connection import build_sql_connection_string
from app.core.odbc_utils import best_driver

_MAX_ATTEMPTS = 3
_BASE_DELAY = 2.0   # seconds; doubles each retry
_JITTER = 0.10      # ±10 %


class SqlClient:
    """pyodbc-based SQL Server client. NOT thread-safe — one instance per thread."""

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._conn: pyodbc.Connection | None = None

    def connect(self) -> None:
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

            except pyodbc.Error as exc:
                last_exc = exc

        sqlstate = last_exc.args[0] if (last_exc and last_exc.args) else "unknown"
        raise ConnectionError(
            f"SQL Server connection failed after {_MAX_ATTEMPTS} attempts "
            f"(SQLSTATE {sqlstate})"
        ) from last_exc

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
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except pyodbc.Error:
            return False

    def query(self, sql: str, params: tuple = ()) -> QueryResult:
        if self._conn is None:
            raise RuntimeError("Not connected")
        start = datetime.now(timezone.utc)
        with self._conn.cursor() as cursor:
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
            if not self.is_alive():
                return (False, 'Подключение установлено, но проверка связи не прошла')
            result = self.query(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES"
                " WHERE TABLE_TYPE = 'BASE TABLE'"
            )
            table_count = result.rows[0][0] if result.rows else 0
            return (True, f"Подключено · {table_count} таблиц · {result.duration_ms} мс")
        except ConnectionError as exc:
            # ConnectionError already contains a sanitized message (no DSN)
            return (False, str(exc))
        except Exception:
            return (False, "Неожиданная ошибка при подключении")
        finally:
            self.disconnect()
