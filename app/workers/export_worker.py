"""
ExportWorker — QObject wrapper that runs an :class:`ExportPipeline`
on a background thread and translates its progress / result / failure
into Qt signals.

The heavy lifting lives in :mod:`app.export.pipeline`. This file is
deliberately thin — it exists to bridge the pipeline (plain Python)
with the rest of the app that speaks Qt signals.

Pipeline steps (emitted via progress signal):
    0  Подключение к БД...
    1  Выполнение запроса...
    2  Отправка данных...
    3  Готово
"""

from __future__ import annotations

import json
import logging
import time
import traceback
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig, ExportJob, SyncResult
from app.core.log_sanitizer import mask_secrets
from app.core.sql_client import SqlClient  # noqa: F401 - kept for test monkeypatch compat
from app.export.pipeline import build_pipeline_for_job
from app.export.sinks.google_apps_script import GoogleAppsScriptDeliveryError
# Backwards-compatible re-exports. Callers (incl. tests) historically
# imported these names from this module.
from app.export.sinks.webhook import (  # noqa: F401
    DEFAULT_RETRY_ATTEMPTS as WEBHOOK_RETRY_ATTEMPTS,
    DEFAULT_RETRY_BASE_DELAY as WEBHOOK_RETRY_BASE_DELAY,
    build_webhook_payload,
)

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
        # Resolve SqlClient via module attribute so tests that monkeypatch
        # ``app.workers.export_worker.SqlClient`` still intercept construction.
        sql_client_cls = globals().get("SqlClient", SqlClient)
        pipeline = build_pipeline_for_job(
            self._cfg,
            self._job,
            sql_client_cls=sql_client_cls,
        )
        job_name = self._job.get("name", "?")
        started_ns = time.perf_counter_ns()
        try:
            result = pipeline.run(self._job, progress=self.progress.emit)
            self.finished.emit(result)
        except GoogleAppsScriptDeliveryError as exc:
            self.error.emit(exc.user_message)
            _log.error("Ошибка выгрузки '%s': %s", job_name, exc.user_message)
            debug_context = mask_secrets(
                json.dumps(
                    exc.debug_context,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            )
            _log.debug("GAS debug_context: %s", debug_context)
            tb = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            _log.debug("GAS traceback: %s", mask_secrets(tb))
            self.finished.emit(
                SyncResult(
                    success=False,
                    rows_synced=0,
                    error=exc.user_message,
                    timestamp=datetime.now(timezone.utc),
                    duration_us=max(0, (time.perf_counter_ns() - started_ns) // 1_000),
                    sql_duration_us=0,
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
                    duration_us=max(0, (time.perf_counter_ns() - started_ns) // 1_000),
                    sql_duration_us=0,
                )
            )


__all__ = [
    "ExportWorker",
    "build_webhook_payload",
    "WEBHOOK_RETRY_ATTEMPTS",
    "WEBHOOK_RETRY_BASE_DELAY",
]
