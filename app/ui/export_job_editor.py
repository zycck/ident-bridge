# -*- coding: utf-8 -*-
"""Export job editor widget extracted from ExportJobsWidget."""

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.config import ConfigManager, ExportHistoryEntry, ExportJob, SyncResult
from app.core.app_logger import get_logger
from app.core.constants import DEBOUNCE_SAVE_MS, DEBOUNCE_SYNTAX_MS
from app.core.scheduler import SyncScheduler
from app.ui.export_editor_runtime import ExportEditorRuntimeState
from app.ui.export_editor_shell import ExportEditorShell
from app.ui.export_execution_controller import ExportExecutionController
from app.ui.export_schedule_panel import schedule_value_is_valid
from app.ui.test_run_dialog import TestRunDialog
from app.ui.threading import run_worker
from app.workers.export_worker import ExportWorker

_log = get_logger(__name__)
_FAILURE_ALERT_THRESHOLD = 3


class ExportJobEditor(QWidget):
    """Single export-job editor with its own scheduler and worker thread."""

    changed = Signal(object)
    sync_completed = Signal(object)
    history_changed = Signal()
    failure_alert = Signal(str, int)

    def __init__(
        self,
        job: ExportJob,
        config: ConfigManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._config = config
        self._job_id: str = job.get("id", "")
        self._runtime = ExportEditorRuntimeState()

        self._scheduler = SyncScheduler(self)
        self._scheduler.trigger.connect(self._auto_trigger)

        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(DEBOUNCE_SAVE_MS)
        self._query_timer.timeout.connect(self._emit_changed)

        self._syntax_timer = QTimer(self)
        self._syntax_timer.setSingleShot(True)
        self._syntax_timer.setInterval(DEBOUNCE_SYNTAX_MS)
        self._syntax_timer.timeout.connect(self._refresh_sql_syntax)

        self._build_ui()
        self._execution = ExportExecutionController(
            runtime=self._runtime,
            load_config=self._config.load,
            build_job=self.to_job,
            create_worker=lambda cfg, current_job: ExportWorker(cfg, current_job),
            start_worker=self._start_worker,
            set_run_enabled=self._shell.set_run_enabled,
            set_progress_text=self._shell.set_progress_text,
            set_status=self._shell.set_status,
            add_history_entry=self._add_history_entry,
            emit_sync_completed=self.sync_completed.emit,
            emit_failure_alert=self.failure_alert.emit,
            failure_alert_threshold=_FAILURE_ALERT_THRESHOLD,
        )
        self._load_job(job)
        self._apply_schedule()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._shell = ExportEditorShell(self)
        self._header = self._shell._header
        self._sql_panel = self._shell._sql_panel
        self._webhook_edit = self._shell._webhook_edit
        self._schedule_panel = self._shell._schedule_panel
        self._history_panel = self._shell._history_panel
        self._shell.changed.connect(self._emit_changed)
        self._shell.query_changed.connect(self._on_query_changed)
        self._shell.schedule_changed.connect(self._on_sched_changed)
        self._shell.history_changed.connect(self._on_history_changed)
        self._shell.test_requested.connect(self._open_test_dialog)
        self._shell.run_requested.connect(self.start_export)
        root.addWidget(self._shell)

    def job_id(self) -> str:
        return self._job_id

    def to_job(self) -> ExportJob:
        return ExportJob(
            id=self._job_id,
            name=self._shell.job_name(),
            sql_query=self._shell.sql_text(),
            webhook_url=self._shell.webhook_url(),
            schedule_enabled=self._shell.schedule_enabled(),
            schedule_mode=self._shell.schedule_mode(),
            schedule_value=self._shell.schedule_value(),
            history=self._shell.history(),
        )

    def _load_job(self, job: ExportJob) -> None:
        self._shell.set_job_name(job.get("name", ""))
        self._shell.set_sql_text(job.get("sql_query", ""))
        self._shell.set_webhook_url(job.get("webhook_url", ""))
        self._shell.set_schedule(
            bool(job.get("schedule_enabled", False)),
            job.get("schedule_mode", "daily"),
            job.get("schedule_value", ""),
        )
        self._shell.set_history(list(job.get("history") or []))

        latest = self._shell.latest_history_entry()
        if latest is not None:
            kind, text = self._runtime.status_from_latest_entry(latest)
            self._shell.set_status(kind, text)
        QTimer.singleShot(0, self._refresh_sql_syntax)

    def _on_sched_changed(self) -> None:
        self._apply_schedule()
        self._emit_changed()

    def _apply_schedule(self) -> None:
        self._scheduler.stop()
        if not self._shell.schedule_enabled():
            return
        mode = self._shell.schedule_mode()
        value = self._shell.schedule_value()
        if not schedule_value_is_valid(mode, value):
            return
        self._scheduler.configure(mode, value)  # type: ignore[arg-type]
        self._scheduler.start()
        _log.debug(
            "Job '%s': scheduler started (%s %s)",
            self._shell.job_name() or self._job_id,
            mode,
            value,
        )

    def stop_scheduler(self) -> None:
        self._scheduler.stop()

    def stop_timers(self) -> None:
        if hasattr(self, "_query_timer") and self._query_timer is not None:
            self._query_timer.stop()
        if hasattr(self, "_syntax_timer") and self._syntax_timer is not None:
            self._syntax_timer.stop()

    def _on_query_changed(self) -> None:
        self._query_timer.start()
        self._syntax_timer.start()

    def _refresh_sql_syntax(self) -> None:
        self._shell.refresh_sql_syntax()

    @Slot()
    def _auto_trigger(self) -> None:
        self._execution.start_scheduled()

    def start_export(self) -> None:
        self._execution.start_manual()

    def _start_export(self) -> None:
        self._execution.start_manual()

    def _start_worker(
        self,
        worker: ExportWorker,
        on_finished,
        on_error,
        on_progress,
    ) -> None:
        run_worker(
            self,
            worker,
            pin_attr="_worker",
            on_finished=on_finished,
            on_error=on_error,
        )
        worker.progress.connect(on_progress)

    @Slot(int, str)
    def _on_progress(self, _step: int, description: str) -> None:
        self._execution.on_progress(_step, description)

    @Slot(object)
    def _on_finished(self, result: SyncResult) -> None:
        self._execution.on_finished(result)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._execution.on_error(msg)

    def _add_history_entry(self, entry: ExportHistoryEntry) -> None:
        self._shell.prepend_history_entry(entry)

    def _open_test_dialog(self) -> None:
        sql = self._shell.sql_text()
        cfg = self._config.load()
        dialog = TestRunDialog(
            cfg,
            initial_sql=sql,
            auto_run=bool(sql),
            parent=self,
        )
        dialog.test_completed.connect(self._on_test_completed)
        dialog.exec()

    @Slot(bool, int, str)
    def _on_test_completed(self, ok: bool, rows: int, err: str) -> None:
        self._execution.record_test_completed(ok=ok, rows=rows, err=err)

    def _emit_changed(self) -> None:
        self.changed.emit(self.to_job())

    def _on_history_changed(self) -> None:
        self._emit_changed()
        self.history_changed.emit()

    @property
    def _consecutive_failures(self) -> int:
        return self._execution.consecutive_failures

    @property
    def _running(self) -> bool:
        return self._execution.running
