# -*- coding: utf-8 -*-
"""ExportJobsWidget — list-detail export job manager (tiles + editor pages)."""
from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    ConfigManager,
    ExportHistoryEntry,
    ExportJob,
    SyncResult,
    TriggerType,
)
from app.core.app_logger import get_logger
from app.core.constants import (
    DEBOUNCE_SAVE_MS,
    DEBOUNCE_SYNTAX_MS,
)
from app.core.scheduler import SyncScheduler
from app.ui.export_editor_header import ExportEditorHeader
from app.ui.export_execution_controller import ExportExecutionController
from app.ui.export_history_panel import ExportHistoryPanel
from app.ui.export_job_tile import ExportJobTile
from app.ui.export_jobs_pages import ExportJobsEditorPage, ExportJobsTilesPage
from app.ui.export_editor_runtime import ExportEditorRuntimeState
from app.ui.export_jobs_store import (
    load_export_jobs,
    new_export_job,
    persist_export_jobs,
)
from app.ui.export_schedule_panel import (
    ExportSchedulePanel,
    schedule_value_is_valid,
)
from app.ui.export_sql_panel import ExportSqlPanel
from app.ui.test_run_dialog import TestRunDialog
from app.ui.threading import run_worker
from app.ui.widgets import HeaderLabel, hsep
from app.workers.export_worker import ExportWorker

_log = get_logger(__name__)

# Maps _mode_combo index → schedule_mode string (order must match addItems call)
_FAILURE_ALERT_THRESHOLD = 3


# ---------------------------------------------------------------------------
# ExportJobEditor  (renamed from ExportJobCard)
# ---------------------------------------------------------------------------

class ExportJobEditor(QWidget):
    """Single export-job editor with its own scheduler and worker thread.

    Previously named ExportJobCard. Now used as a full-page editor inside
    a QScrollArea. The objectName is kept as "exportCard" so the existing
    QSS rule in theme.qss continues to apply without changes.
    """

    changed          = Signal(object)  # ExportJob — emitted on any field edit
    sync_completed   = Signal(object)  # SyncResult — emitted on successful run
    history_changed  = Signal()        # emitted whenever an entry is added or deleted
    failure_alert    = Signal(str, int)  # (job_name, consecutive_failures) — tray notification

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

        # debounce — save after user stops typing in SQL/name/webhook
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(DEBOUNCE_SAVE_MS)
        self._query_timer.timeout.connect(self._emit_changed)

        # debounce — syntax check
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
            set_run_enabled=self._header.set_run_enabled,
            set_progress_text=self._schedule_panel.set_progress_text,
            set_status=self._header.set_status,
            add_history_entry=self._add_history_entry,
            emit_sync_completed=self.sync_completed.emit,
            emit_failure_alert=self.failure_alert.emit,
            failure_alert_threshold=_FAILURE_ALERT_THRESHOLD,
        )
        self._load_job(job)
        self._apply_schedule()

    # ------------------------------------------------------------------ UI

    @staticmethod
    def _section_break(root: "QVBoxLayout") -> None:
        """Add a horizontal separator with breathing room above and below."""
        root.addSpacing(8)
        root.addWidget(hsep())
        root.addSpacing(8)

    def _build_ui(self) -> None:
        """Compose the editor UI from sub-section builders."""
        self.setObjectName("exportCard")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        self._build_header(root)
        self._section_break(root)
        self._build_sql_section(root)
        self._section_break(root)
        self._build_webhook_section(root)
        self._section_break(root)
        self._build_schedule_section(root)
        self._build_history_section(root)

    def _build_header(self, root: QVBoxLayout) -> None:
        """Header row: title + status summary + Тест/Запустить buttons."""
        self._header = ExportEditorHeader(self)
        self._header.changed.connect(self._emit_changed)
        self._header.test_requested.connect(self._open_test_dialog)
        self._header.run_requested.connect(self.start_export)
        root.addWidget(self._header)

    def _build_sql_section(self, root: QVBoxLayout) -> None:
        """SQL editor + syntax indicator."""
        self._sql_panel = ExportSqlPanel(self)
        self._sql_panel.changed.connect(self._on_query_changed)
        root.addWidget(self._sql_panel, stretch=1)

    def _build_webhook_section(self, root: QVBoxLayout) -> None:
        """Webhook URL label + input."""
        root.addWidget(HeaderLabel("Webhook URL"))

        self._webhook_edit = QLineEdit()
        self._webhook_edit.setPlaceholderText("https://… (необязательно)")
        self._webhook_edit.editingFinished.connect(self._emit_changed)
        root.addWidget(self._webhook_edit)

    def _build_schedule_section(self, root: QVBoxLayout) -> None:
        self._schedule_panel = ExportSchedulePanel(self)
        self._schedule_panel.changed.connect(self._on_sched_changed)
        root.addWidget(self._schedule_panel)

    def _build_history_section(self, root: QVBoxLayout) -> None:
        """History group with its own data/UI component."""
        self._history_panel = ExportHistoryPanel(self)
        self._history_panel.changed.connect(self._emit_changed)
        self._history_panel.changed.connect(self.history_changed)
        root.addWidget(self._history_panel)

    # ------------------------------------------------------------------ Load / save

    def job_id(self) -> str:
        return self._job_id

    def to_job(self) -> ExportJob:
        return ExportJob(
            id=self._job_id,
            name=self._header.job_name(),
            sql_query=self._sql_panel.sql_text(),
            webhook_url=self._webhook_edit.text().strip(),
            schedule_enabled=self._schedule_panel.schedule_enabled(),
            schedule_mode=self._schedule_panel.schedule_mode(),
            schedule_value=self._schedule_panel.schedule_value(),
            history=self._history_panel.history(),
        )

    def _load_job(self, job: ExportJob) -> None:
        self._header.set_job_name(job.get("name", ""))
        self._sql_panel.set_sql_text(job.get("sql_query", ""))
        self._webhook_edit.blockSignals(True)
        self._webhook_edit.setText(job.get("webhook_url", ""))
        self._schedule_panel.set_schedule(
            bool(job.get("schedule_enabled", False)),
            job.get("schedule_mode", "daily"),
            job.get("schedule_value", ""),
        )
        self._history_panel.set_history(list(job.get("history") or []))
        self._webhook_edit.blockSignals(False)

        latest = self._history_panel.latest_entry()
        # Restore status summary from most recent history entry (if any)
        if latest is not None:
            kind, text = self._runtime.status_from_latest_entry(latest)
            self._header.set_status(kind, text)
        # Trigger syntax check after layout settles
        QTimer.singleShot(0, self._refresh_sql_syntax)

    # ------------------------------------------------------------------ Schedule

    def _on_sched_changed(self) -> None:
        self._apply_schedule()
        self._emit_changed()

    def _apply_schedule(self) -> None:
        """Start or stop this editor's scheduler based on current UI settings."""
        self._scheduler.stop()
        if not self._schedule_panel.schedule_enabled():
            return
        mode = self._schedule_panel.schedule_mode()
        value = self._schedule_panel.schedule_value()
        if not schedule_value_is_valid(mode, value):
            return
        self._scheduler.configure(mode, value)  # type: ignore[arg-type]
        self._scheduler.start()
        _log.debug(
            "Job '%s': scheduler started (%s %s)",
            self._header.job_name() or self._job_id, mode, value,
        )

    def stop_scheduler(self) -> None:
        self._scheduler.stop()

    def stop_timers(self) -> None:
        """Stop the debounce timers — call before deleteLater()."""
        if hasattr(self, "_query_timer") and self._query_timer is not None:
            self._query_timer.stop()
        if hasattr(self, "_syntax_timer") and self._syntax_timer is not None:
            self._syntax_timer.stop()

    # ------------------------------------------------------------------ SQL validation

    def _on_query_changed(self) -> None:
        self._query_timer.start()
        self._syntax_timer.start()

    def _refresh_sql_syntax(self) -> None:
        self._sql_panel.refresh_syntax()

    # ------------------------------------------------------------------ Export

    @Slot()
    def _auto_trigger(self) -> None:
        """Called by scheduler — marks trigger as scheduled then fires export."""
        self._execution.start_scheduled()

    def start_export(self) -> None:
        """Public API — manual trigger; idempotent."""
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

    # ------------------------------------------------------------------ Worker slots

    @Slot(int, str)
    def _on_progress(self, _step: int, description: str) -> None:
        self._execution.on_progress(_step, description)

    @Slot(object)
    def _on_finished(self, result: SyncResult) -> None:
        self._execution.on_finished(result)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._execution.on_error(msg)

    # ------------------------------------------------------------------ History data

    def _add_history_entry(self, entry: ExportHistoryEntry) -> None:
        self._history_panel.prepend_entry(entry)

    # ------------------------------------------------------------------ Test dialog

    def _open_test_dialog(self) -> None:
        sql = self._sql_panel.sql_text()
        cfg = self._config.load()
        dialog = TestRunDialog(
            cfg,
            initial_sql=sql,
            auto_run=bool(sql),   # execute immediately if SQL is present
            parent=self,
        )
        dialog.test_completed.connect(self._on_test_completed)
        dialog.exec()

    @Slot(bool, int, str)
    def _on_test_completed(self, ok: bool, rows: int, err: str) -> None:
        """Record a TestRunDialog run as a TEST-trigger history entry."""
        self._execution.record_test_completed(ok=ok, rows=rows, err=err)

    # ------------------------------------------------------------------ Signals

    def _emit_changed(self) -> None:
        self.changed.emit(self.to_job())

    @property
    def _consecutive_failures(self) -> int:
        """Compatibility shim for existing tests during the decomposition wave."""
        return self._execution.consecutive_failures

    @property
    def _running(self) -> bool:
        """Compatibility shim for callers that still probe the editor directly."""
        return self._execution.running


# ---------------------------------------------------------------------------
# ExportJobsWidget
# ---------------------------------------------------------------------------

class ExportJobsWidget(QWidget):
    """Container for export jobs: list of tiles + detail editor pages."""

    sync_completed  = Signal(object)  # SyncResult — bubbled up from any editor
    history_changed = Signal()         # bubbled up from any editor
    failure_alert   = Signal(str, int)  # (job_name, consecutive_count) — wire to tray in MainWindow

    def __init__(self, config: ConfigManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config
        self._editors: dict[str, ExportJobEditor] = {}
        self._current_editor_id: str | None = None
        self._build_ui()
        self._load_jobs()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._tiles_page = ExportJobsTilesPage(self)
        self._tiles_page.add_requested.connect(self._add_new_job)
        self._editor_page = ExportJobsEditorPage(self)
        self._editor_page.back_requested.connect(self._show_tiles)
        self._editor_page.delete_requested.connect(self._delete_current_editor)
        self._stack.addWidget(self._tiles_page)   # index 0
        self._stack.addWidget(self._editor_page)  # index 1

    # ------------------------------------------------------------------ Jobs CRUD

    def _load_jobs(self) -> None:
        for job in load_export_jobs(self._config):
            self._add_tile(job)
            # Pre-create the editor so the scheduler runs even when not in
            # the editor view — same as the old ExportJobCard which lived
            # in the layout permanently.
            self._editors[job["id"]] = self._create_editor(job)
        self._tiles_page.refresh_empty()
        self._tiles_page.reflow_tiles()

    def _save_jobs(self) -> None:
        persist_export_jobs(
            self._config,
            [ed.to_job() for ed in self._editors.values()],
        )
        # Refresh the corresponding tile labels
        for ed in self._editors.values():
            job = ed.to_job()
            for tile in self._tiles_page.tiles():
                if tile.job_id() == job.get("id"):
                    tile.update_from_job(job)
                    break

    def _add_new_job(self) -> None:
        job = new_export_job()
        self._add_tile(job)
        self._editors[job["id"]] = self._create_editor(job)
        self._save_jobs()
        self._tiles_page.refresh_empty()
        self._tiles_page.reflow_tiles()
        # Open the editor immediately so the user can fill in the name/SQL
        self._show_editor(job["id"])

    def _add_tile(self, job: ExportJob) -> None:
        tile = ExportJobTile(job, self)
        tile.open_requested.connect(self._show_editor)
        tile.run_requested.connect(self._run_job)
        tile.delete_requested.connect(self._on_tile_delete)
        self._tiles_page.add_tile(tile)

    def _create_editor(self, job: ExportJob) -> ExportJobEditor:
        editor = ExportJobEditor(job, self._config, self)
        editor.changed.connect(lambda _j: self._save_jobs())
        editor.history_changed.connect(self.history_changed)
        editor.history_changed.connect(self._save_jobs)
        editor.sync_completed.connect(self.sync_completed)
        editor.failure_alert.connect(self.failure_alert)

        # Wrap in a container with padding, then in a QScrollArea page
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(container)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(0)
        cl.addWidget(editor, stretch=1)   # editor takes ALL extra space — no addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(container)

        self._editor_page.add_editor(job.get("id", ""), scroll)

        return editor

    @Slot(str)
    def _show_editor(self, job_id: str) -> None:
        editor = self._editors.get(job_id)
        if editor is None:
            return
        if not self._editor_page.show_editor(job_id):
            return
        self._current_editor_id = job_id
        self._stack.setCurrentIndex(1)

    @Slot()
    def _show_tiles(self) -> None:
        self._current_editor_id = None
        self._stack.setCurrentIndex(0)
        # Refresh tile labels to reflect any edits made in the editor
        for ed in self._editors.values():
            job = ed.to_job()
            for tile in self._tiles_page.tiles():
                if tile.job_id() == job.get("id"):
                    tile.update_from_job(job)
                    break

    @Slot()
    def _delete_current_editor(self) -> None:
        if self._current_editor_id is None:
            return
        self._on_tile_delete(self._current_editor_id)

    @Slot(str)
    def _run_job(self, job_id: str) -> None:
        editor = self._editors.get(job_id)
        if editor is not None:
            editor.start_export()

    @Slot(str)
    def _on_tile_delete(self, job_id: str) -> None:
        editor = self._editors.get(job_id)
        if editor is not None and getattr(editor, "_running", False):
            QMessageBox.warning(
                self,
                "Выгрузка выполняется",
                "Дождитесь завершения выгрузки перед удалением.",
            )
            return
        name = "без названия"
        if editor is not None:
            name = editor.to_job().get("name") or "без названия"
        reply = QMessageBox.question(
            self,
            "Удалить выгрузку",
            f"Удалить выгрузку «{name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # Stop scheduler, remove editor + scroll page from internal stack
        if editor is not None:
            editor.stop_scheduler()
            editor.stop_timers()         # stop debounce timers before deleteLater()
            scroll = self._editor_page.remove_editor(job_id)
            if scroll is not None:
                scroll.deleteLater()
            editor.deleteLater()
            del self._editors[job_id]
        tile = self._tiles_page.remove_tile(job_id)
        if tile is not None:
            tile.deleteLater()
        # If the deleted job was the one currently shown in the editor,
        # navigate back to the tiles list
        if self._current_editor_id == job_id:
            self._show_tiles()
        self._save_jobs()
        self._tiles_page.refresh_empty()
        self._tiles_page.reflow_tiles()
        self.history_changed.emit()

    # ------------------------------------------------------------------ Public

    def stop_all_schedulers(self) -> None:
        """Stop all per-job schedulers — call on app shutdown."""
        for editor in self._editors.values():
            editor.stop_scheduler()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        """Safety net: stop schedulers + timers if the widget is closed
        independently of the app's normal aboutToQuit cleanup hook."""
        self.stop_all_schedulers()
        for editor in self._editors.values():
            editor.stop_timers()
        super().closeEvent(event)
