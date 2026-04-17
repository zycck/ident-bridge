"""Lifecycle/timer orchestration extracted from ExportJobEditor."""

from collections.abc import Callable

from PySide6.QtCore import QTimer, Slot

from app.config import ExportHistoryEntry, ExportJob
from app.core.app_logger import get_logger
from app.core.scheduler import SyncScheduler, schedule_value_is_valid
from app.ui.export_editor_runtime import ExportEditorRuntimeState

_log = get_logger(__name__)


class ExportEditorController:
    """Owns non-visual lifecycle wiring around the export editor shell."""

    def __init__(
        self,
        *,
        shell,
        scheduler: SyncScheduler,
        query_timer: QTimer,
        syntax_timer: QTimer,
        load_config: Callable[[], dict],
        emit_changed: Callable[[], None],
        emit_history_changed: Callable[[], None],
        run_manual_export: Callable[[], None],
        run_scheduled_export: Callable[[], None],
        record_test_completed: Callable[..., None],
        create_test_dialog: Callable[[dict, str], object],
        status_from_latest_entry: Callable[[ExportHistoryEntry], tuple[str, str]] = ExportEditorRuntimeState.status_from_latest_entry,
    ) -> None:
        self._shell = shell
        self._scheduler = scheduler
        self._query_timer = query_timer
        self._syntax_timer = syntax_timer
        self._load_config = load_config
        self._emit_changed = emit_changed
        self._emit_history_changed = emit_history_changed
        self._run_manual_export = run_manual_export
        self._run_scheduled_export = run_scheduled_export
        self._record_test_completed = record_test_completed
        self._create_test_dialog = create_test_dialog
        self._status_from_latest_entry = status_from_latest_entry

    def wire(self) -> None:
        self._scheduler.trigger.connect(self.start_scheduled_export)
        self._query_timer.timeout.connect(self._emit_changed)
        self._syntax_timer.timeout.connect(self.refresh_sql_syntax)
        self._shell.changed.connect(self._emit_changed)
        self._shell.query_changed.connect(self.handle_query_changed)
        self._shell.schedule_changed.connect(self.handle_schedule_changed)
        self._shell.history_changed.connect(self.handle_history_changed)
        self._shell.test_requested.connect(self.open_test_dialog)
        self._shell.run_requested.connect(self.start_export)

    def load_job(self, job: ExportJob) -> None:
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
            kind, text = self._status_from_latest_entry(latest)
            self._shell.set_status(kind, text)

        self.apply_schedule()

    @Slot()
    def handle_schedule_changed(self) -> None:
        self.apply_schedule()
        self._emit_changed()

    def apply_schedule(self) -> None:
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
            self._shell.job_name(),
            mode,
            value,
        )

    def stop_scheduler(self) -> None:
        self._scheduler.stop()

    def stop_timers(self) -> None:
        self._query_timer.stop()
        self._syntax_timer.stop()

    def handle_query_changed(self) -> None:
        self._query_timer.start()
        self._syntax_timer.start()

    def refresh_sql_syntax(self) -> None:
        self._shell.refresh_sql_syntax()

    @Slot()
    def start_scheduled_export(self) -> None:
        self._run_scheduled_export()

    def start_export(self) -> None:
        self._run_manual_export()

    def open_test_dialog(self) -> None:
        sql = self._shell.sql_text()
        dialog = self._create_test_dialog(self._load_config(), sql)
        dialog.test_completed.connect(self._on_test_completed)
        dialog.exec()

    @Slot(bool, int, str)
    def _on_test_completed(self, ok: bool, rows: int, err: str) -> None:
        self._record_test_completed(ok=ok, rows=rows, err=err)

    def handle_history_changed(self) -> None:
        self._emit_changed()
        self._emit_history_changed()
