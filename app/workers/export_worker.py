"""
ExportWorker — full sync pipeline in a worker thread (moveToThread pattern).

Pipeline steps (emitted via progress signal):
    0  Подключение к БД...
    1  Выполнение запроса...
    2  Отправка данных...
    3  Готово
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig, ExportJob, SyncResult
from app.core.constants import MAX_WEBHOOK_ROWS
from app.core.sql_client import SqlClient

_log = logging.getLogger(__name__)

# Retry policy for webhook POST
WEBHOOK_RETRY_ATTEMPTS: int = 3
WEBHOOK_RETRY_BASE_DELAY: float = float(
    os.environ.get("IDENTBRIDGE_WEBHOOK_RETRY_DELAY", "2.0")
)


class ExportWorker(QObject):
    """QObject worker that runs the SQL query → (optional) webhook pipeline."""

    # (step 0-3, human-readable description)
    progress: Signal = Signal(int, str)
    # Emitted on both success and failure; carries SyncResult
    finished: Signal = Signal(object)
    # Emitted only on failure
    error: Signal = Signal(str)

    def __init__(self, base_cfg: AppConfig, job: ExportJob) -> None:
        super().__init__()
        self._cfg = base_cfg
        self._job = job

    @Slot()
    def run(self) -> None:
        """Execute the SQL → webhook pipeline."""
        sql_client = SqlClient(self._cfg)
        job_name = self._job.get("name", "?")
        try:
            self.progress.emit(0, "Подключение к БД...")
            sql_client.connect()

            self.progress.emit(1, "Выполнение запроса...")
            sql = (self._job.get("sql_query") or "").strip()
            if not sql:
                raise ValueError("SQL запрос не задан в карточке выгрузки")
            result = sql_client.query(sql)

            self.progress.emit(2, "Отправка данных...")
            webhook_url = (self._job.get("webhook_url") or "").strip()
            if webhook_url:
                if result.count > MAX_WEBHOOK_ROWS:
                    msg = (
                        f"Слишком много строк для webhook ({result.count} > "
                        f"{MAX_WEBHOOK_ROWS}). Сократите запрос."
                    )
                    _log.error(msg)
                    raise ValueError(msg)
                last_exc: Exception | None = None
                for attempt in range(1, WEBHOOK_RETRY_ATTEMPTS + 1):
                    try:
                        payload = json.dumps({
                            "job":     job_name,
                            "rows":    result.count,
                            "columns": result.columns,
                            "data":    [list(row) for row in result.rows],
                        }, ensure_ascii=False, default=str).encode("utf-8")
                        req = urllib.request.Request(
                            webhook_url,
                            data=payload,
                            headers={
                                "Content-Type": "application/json; charset=utf-8",
                                "User-Agent":   "iDentBridge",
                            },
                            method="POST",
                        )
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            _log.info(
                                "Webhook %s → HTTP %d (attempt %d)",
                                webhook_url, resp.status, attempt,
                            )
                            last_exc = None
                            break
                    except Exception as exc:
                        last_exc = exc
                        _log.warning(
                            "Webhook attempt %d/%d failed: %s",
                            attempt, WEBHOOK_RETRY_ATTEMPTS, exc,
                        )
                        if attempt < WEBHOOK_RETRY_ATTEMPTS:
                            time.sleep(WEBHOOK_RETRY_BASE_DELAY * (2 ** (attempt - 1)))
                if last_exc is not None:
                    _log.error("Webhook push failed after %d attempts: %s", WEBHOOK_RETRY_ATTEMPTS, last_exc)
                    raise last_exc
                _log.info("Выгрузка '%s': %d строк → webhook %s", job_name, result.count, webhook_url)
            else:
                _log.info("Выгрузка '%s': %d строк (webhook не настроен)", job_name, result.count)

            self.progress.emit(3, "Готово")
            self.finished.emit(
                SyncResult(
                    success=True,
                    rows_synced=result.count,
                    error=None,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            _log.error("Ошибка выгрузки '%s': %s", job_name, msg)
            self.error.emit(msg)
            self.finished.emit(
                SyncResult(
                    success=False,
                    rows_synced=0,
                    error=msg,
                    timestamp=datetime.now(timezone.utc),
                )
            )

        finally:
            sql_client.disconnect()
