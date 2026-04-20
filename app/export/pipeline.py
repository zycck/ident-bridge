"""Connect → query → deliver pipeline.

The pipeline is a plain callable (not a QObject) so it can be unit
tested without a Qt event loop. :class:`~app.workers.export_worker.ExportWorker`
is the QObject wrapper that adapts :meth:`ExportPipeline.run` into
Qt signals.

Responsibilities:
- Call ``db.connect()`` once, ``db.disconnect()`` in ``finally`` once.
- Run one SQL query against that connection.
- Hand the result to the sink (if any).
- Emit progress through a callback so the caller (usually a QObject)
  can translate that into signals or log lines.

Error handling is intentionally minimal — the pipeline converts no
exceptions. The worker catches and translates to signals; unit tests
catch and assert directly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from app.config import AppConfig, ExportJob, QueryResult, SyncResult
from app.core.constants import GOOGLE_SCRIPT_HOSTS, MAX_WEBHOOK_ROWS
from app.core.sql_client import SqlClient
from app.export.protocol import ExportSink
from app.export.sinks.google_apps_script import GoogleAppsScriptSink
from app.export.sinks.webhook import WebhookSink
from app.ui.formatters import format_duration_compact

_log = logging.getLogger(__name__)

# ProgressCallback: step_number (0–3), human-readable message.
ProgressCallback = Callable[[int, str], None]


def _noop_progress(step: int, message: str) -> None:
    pass


@dataclass(slots=True)
class ExportPipeline:
    """Stateless pipeline of ``connect → query → (optional) sink``.

    A fresh pipeline should be constructed for each run — the database
    client inside is single-use.
    """

    db: Any                       # DatabaseClient-like (SqlClient today)
    sink: ExportSink | None
    logger: logging.Logger = field(default_factory=lambda: _log)

    def run(
        self,
        job: ExportJob,
        progress: ProgressCallback = _noop_progress,
    ) -> SyncResult:
        """Execute the pipeline end-to-end and return a :class:`SyncResult`."""
        job_name = job.get("name", "?")
        sql = (job.get("sql_query") or "").strip()
        if not sql:
            raise ValueError("SQL запрос не задан в карточке выгрузки")
        started_ns = time.perf_counter_ns()

        try:
            progress(0, "Подключение к БД...")
            # connect() lives inside the try so disconnect() still fires
            # when the initial connect itself raises (matches the pre-refactor
            # behaviour — see test_db_connect_failure_disconnect_still_called).
            self.db.connect()

            progress(1, "Выполнение запроса...")
            result: QueryResult = self.db.query(sql)

            progress(2, "Отправка данных...")
            if self.sink is not None:
                self.sink.push(
                    job_name,
                    result,
                    on_progress=lambda text: progress(2, text),
                )
            else:
                self.logger.info(
                    "Выгрузка '%s': %d строк за %s (webhook не настроен)",
                    job_name,
                    result.count,
                    format_duration_compact(result.duration_us),
                )

            progress(3, "Готово")
            total_duration_us = max(
                result.duration_us,
                max(0, (time.perf_counter_ns() - started_ns) // 1_000),
            )
            return SyncResult(
                success=True,
                rows_synced=result.count,
                error=None,
                timestamp=datetime.now(timezone.utc),
                duration_us=total_duration_us,
                sql_duration_us=result.duration_us,
            )
        finally:
            self.db.disconnect()


def build_pipeline_for_job(
    cfg: AppConfig,
    job: ExportJob,
    *,
    sql_client_cls: type = SqlClient,
) -> ExportPipeline:
    """Factory: assemble the default pipeline for a job.

    Single registration point for which sink handles which job type.
    Extend this function (or replace the factory call-site) when a new
    sink type lands.

    ``sql_client_cls`` is accepted as a keyword for tests and future
    DatabaseClient-factory wiring (see audit plan I.4).
    """
    db = sql_client_cls(cfg)
    sink = resolve_export_sink(
        job.get("webhook_url") or "",
        gas_options=job.get("gas_options"),
    )

    return ExportPipeline(db=db, sink=sink)


def resolve_export_sink(webhook_url: str, *, gas_options: dict[str, Any] | None = None) -> ExportSink | None:
    """Return the appropriate sink for a configured export URL."""
    url = webhook_url.strip()
    if not url:
        return None

    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if host in GOOGLE_SCRIPT_HOSTS:
        return GoogleAppsScriptSink(url, gas_options=gas_options)
    return WebhookSink(url, max_rows=MAX_WEBHOOK_ROWS)


__all__ = [
    "ExportPipeline",
    "ProgressCallback",
    "build_pipeline_for_job",
    "resolve_export_sink",
]
