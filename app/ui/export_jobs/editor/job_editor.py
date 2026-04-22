"""Export job editor widget extracted from ExportJobsWidget."""

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from app.config import ConfigManager, ExportHistoryEntry, ExportJob, SyncResult
from app.core.constants import DEBOUNCE_SAVE_MS, DEBOUNCE_SYNTAX_MS
from app.core.scheduler import SyncScheduler
from app.export.run_store import ExportRunStore
from app.ui.export_editor_controller import ExportEditorController
from app.ui.export_job_editor_bridge import ExportJobEditorBridge
from app.ui.export_editor_runtime import ExportEditorRuntimeState
from app.ui.export_jobs.status_summary import build_unfinished_run_status, latest_unfinished_run
from app.ui.export_editor_shell import ExportEditorShell
from app.ui.export_execution_controller import ExportExecutionController
from app.workers.export_worker import ExportWorker

_FAILURE_ALERT_THRESHOLD = 3


class ExportJobEditor(QWidget):
    """Single export-job editor with its own scheduler and worker thread."""

    changed = Signal(object)
    sync_completed = Signal(object)
    history_changed = Signal()
    failure_alert = Signal(str, int)
    runtime_state_changed = Signal(str, str, bool)

    def __init__(
        self,
        job: ExportJob,
        config: ConfigManager,
        run_store: ExportRunStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._config = config
        self._run_store = run_store or ExportRunStore()
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
        self._bridge = ExportJobEditorBridge(
            owner=self,
            shell=self._shell,
            job_id=self._job_id,
            run_store=self._run_store,
        )
        self._shell.set_history_delete_handler(self._run_store.delete_history_entry)
        self._shell.set_history_clear_handler(lambda: self._run_store.clear_job_history(self._job_id))
        self._shell.set_unfinished_retry_handler(self._retry_unfinished_run)
        self._shell.set_unfinished_reset_handler(self._reset_unfinished_run)
        self._shell.set_unfinished_delete_handler(self._delete_unfinished_run)
        self._execution = ExportExecutionController(
            parent=self,
            runtime=self._runtime,
            load_config=self._config.load,
            build_job=self._bridge.build_job,
            create_worker=lambda cfg, current_job: ExportWorker(cfg, current_job),
            start_worker=self._bridge.start_worker,
            set_run_enabled=self._shell.set_run_enabled,
            set_run_busy=self._shell.set_run_busy,
            set_progress_text=self._shell.set_progress_text,
            set_status=self._shell.set_status,
            set_history=self._shell.set_history,
            set_unfinished=self._shell.set_unfinished_runs,
            emit_runtime_state_changed=self.runtime_state_changed.emit,
            load_history=lambda: self._run_store.list_job_history(self._job_id),
            load_unfinished=lambda: self._run_store.list_unfinished_runs(job_id=self._job_id),
            record_history_entry=self._bridge.record_history_entry,
            record_error_entry=lambda _entry: None,
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
            load_history=lambda: self._run_store.list_job_history(self._job_id),
            load_unfinished=lambda: self._run_store.list_unfinished_runs(job_id=self._job_id),
            emit_changed=self._emit_changed,
            emit_history_changed=self.history_changed.emit,
            run_manual_export=self._execution.start_manual,
            run_scheduled_export=self._execution.start_scheduled,
            record_test_completed=self._execution.record_test_completed,
            create_test_dialog=self._bridge.create_test_dialog,
        )
        self._controller.wire()
        self._controller.load_job(job)
        self._refresh_journal_views()

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
        return self._bridge.job_id()

    def to_job(self) -> ExportJob:
        return self._bridge.build_job()

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

    def start_export(self) -> bool:
        return self._controller.start_export()

    def _start_export(self) -> bool:
        return self._controller.start_export()

    @Slot(int, str)
    def _on_progress(self, _step: int, description: str) -> None:
        self._execution.on_progress(_step, description)

    @Slot(object)
    def _on_finished(self, result: SyncResult) -> None:
        self._execution.on_finished(result)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._execution.on_error(msg)

    def _open_test_dialog(self) -> None:
        self._controller.open_test_dialog()

    @Slot(bool, int, str)
    def _on_test_completed(self, ok: bool, rows: int, err: str) -> None:
        self._execution.record_test_completed(ok=ok, rows=rows, err=err)

    def _emit_changed(self) -> None:
        self.changed.emit(self.to_job())

    def _on_history_changed(self) -> None:
        self._controller.handle_history_changed()

    def _refresh_journal_views(self) -> None:
        history = self._run_store.list_job_history(self._job_id)
        unfinished = self._run_store.list_unfinished_runs(job_id=self._job_id)
        self._shell.set_history(history)
        self._shell.set_unfinished_runs(unfinished)

        active_run = latest_unfinished_run(unfinished)
        if active_run is not None:
            kind, text, _ = build_unfinished_run_status(active_run, max_error_length=70)
            self._shell.set_status(kind, text)
            return

        latest = history[0] if history else None
        if latest is not None:
            kind, text = self._runtime.status_from_latest_entry(latest)
            self._shell.set_status(kind, text)
            return

        self._shell.set_status("idle", "\u0415\u0449\u0451 \u043d\u0435 \u0437\u0430\u043f\u0443\u0441\u043a\u0430\u043b\u043e\u0441\u044c")

    def _retry_unfinished_run(self, _run_id: str) -> bool:
        return self.start_export()

    def _reset_unfinished_run(self, run_id: str) -> bool:
        changed = self._run_store.mark_abandoned(run_id)
        if changed:
            self._refresh_journal_views()
        return changed

    def _delete_unfinished_run(self, run_id: str) -> bool:
        changed = self._run_store.delete_run(run_id)
        if changed:
            self._refresh_journal_views()
        return changed

    @property
    def _consecutive_failures(self) -> int:
        return self._execution.consecutive_failures

    @property
    def _running(self) -> bool:
        return self._execution.running
