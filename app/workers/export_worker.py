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

import json
import logging
import time
import traceback
from datetime import UTC, datetime
from typing import final

from PySide6.QtCore import QObject, Signal, Slot

from app.config import AppConfig, ExportJob, SyncResult
from app.core.log_sanitizer import mask_secrets
from app.core.sql_client import SqlClient  # noqa: F401 - kept for test monkeypatch compat
from app.export.pipeline import build_pipeline_for_job
from app.export.sinks.google_apps_script import GoogleAppsScriptDeliveryError
from app.export.sinks.webhook import build_webhook_payload

_log = logging.getLogger(__name__)


@final
class ExportWorker(QObject):
    """QObject worker that runs the SQL query → (optional) webhook pipeline."""

    # (step 0-3, human-readable description)
    progress: Signal = Signal(int, str)
    # Emitted on both success and failure; carries SyncResult
    finished: Signal = Signal(object)
    # Emitted only on failure
    error: Signal = Signal(str)

    def __init__(
        self,
        base_cfg: AppConfig,
        job: ExportJob,
        *,
        trigger: str = "manual",
    ) -> None:
        super().__init__()
        self._cfg = base_cfg
        self._job = job
        self._trigger = str(trigger or "manual").strip() or "manual"

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
            result = pipeline.run(
                self._job,
                progress=self.progress.emit,
                trigger=self._trigger,
            )
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
                    timestamp=datetime.now(UTC),
                    duration_us=max(0, (time.perf_counter_ns() - started_ns) // 1_000),
                    sql_duration_us=0,
                    run_id=exc.run_id,
                    journaled=True,
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
                    timestamp=datetime.now(UTC),
                    duration_us=max(0, (time.perf_counter_ns() - started_ns) // 1_000),
                    sql_duration_us=0,
                    journaled=False,
                )
            )


__all__ = [
    "ExportWorker",
    "build_webhook_payload",
]
