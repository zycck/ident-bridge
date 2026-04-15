"""
ExportWorker — full sync pipeline in a worker thread (moveToThread pattern).

Pipeline steps (emitted via progress signal):
    0  Подключение к БД...
    1  Выполнение запроса...
    2  Отправка данных...
    3  Готово
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig, ExportJob, SyncResult
from app.core.sql_client import SqlClient

_log = logging.getLogger(__name__)


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
                # TODO: implement HTTP push
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
