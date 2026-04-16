# -*- coding: utf-8 -*-
"""Export job editor widget extracted from ExportJobsWidget."""

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.config import ConfigManager, ExportHistoryEntry, ExportJob, SyncResult
from app.core.constants import DEBOUNCE_SAVE_MS, DEBOUNCE_SYNTAX_MS
from app.core.scheduler import SyncScheduler
from app.ui.export_editor_controller import ExportEditorController
from app.ui.export_editor_runtime import ExportEditorRuntimeState
from app.ui.export_editor_shell import ExportEditorShell
from app.ui.export_execution_controller import ExportExecutionController
from app.ui.test_run_dialog import TestRunDialog
from app.ui.threading import run_worker
from app.workers.export_worker import ExportWorker

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
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(DEBOUNCE_SAVE_MS)
        self._syntax_timer = QTimer(self)
        self._syntax_timer.setSingleShot(True)
        self._syntax_timer.setInterval(DEBOUNCE_SYNTAX_MS)
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
        self._controller = ExportEditorController(
            shell=self._shell,
            scheduler=self._scheduler,
            query_timer=self._query_timer,
            syntax_timer=self._syntax_timer,
            load_config=self._config.load,
            emit_changed=self._emit_changed,
            emit_history_changed=self.history_changed.emit,
            run_manual_export=self._execution.start_manual,
            run_scheduled_export=self._execution.start_scheduled,
            record_test_completed=self._execution.record_test_completed,
            create_test_dialog=self._create_test_dialog,
        )
        self._controller.wire()
        self._controller.load_job(job)

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

    def _on_sched_changed(self) -> None:
        self._controller.handle_schedule_changed()

    def _apply_schedule(self) -> None:
        self._controller.apply_schedule()

    def stop_scheduler(self) -> None:
        self._controller.stop_scheduler()

    def stop_timers(self) -> None:
        self._controller.stop_timers()

    def _on_query_changed(self) -> None:
        self._controller.handle_query_changed()

    def _refresh_sql_syntax(self) -> None:
        self._controller.refresh_sql_syntax()

    @Slot()
    def _auto_trigger(self) -> None:
        self._controller.start_scheduled_export()

    def start_export(self) -> None:
        self._controller.start_export()

    def _start_export(self) -> None:
        self._controller.start_export()

    def _start_worker(
        self,
        worker: ExportWorker,
        on_finished,
        on_error,
        on_progress,
    ) -> None:
        worker.progress.connect(on_progress)
        run_worker(
            self,
            worker,
            pin_attr="_worker",
            on_finished=on_finished,
            on_error=on_error,
        )

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
        self._controller.open_test_dialog()

    @Slot(bool, int, str)
    def _on_test_completed(self, ok: bool, rows: int, err: str) -> None:
        self._execution.record_test_completed(ok=ok, rows=rows, err=err)

    def _emit_changed(self) -> None:
        self.changed.emit(self.to_job())

    def _on_history_changed(self) -> None:
        self._controller.handle_history_changed()

    @property
    def _consecutive_failures(self) -> int:
        return self._execution.consecutive_failures

    @property
    def _running(self) -> bool:
        return self._execution.running

    def _create_test_dialog(self, cfg: dict, sql: str) -> TestRunDialog:
        return TestRunDialog(
            cfg,
            initial_sql=sql,
            auto_run=bool(sql),
            parent=self,
        )
