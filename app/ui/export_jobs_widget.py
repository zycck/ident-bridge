# -*- coding: utf-8 -*-
"""ExportJobsWidget — list-detail export job manager (tiles + editor pages)."""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    ConfigManager,
    ExportJob,
)
from app.ui.export_jobs_collection_controller import ExportJobsCollectionController
from app.ui.export_jobs_delete_controller import ExportJobsDeleteController
from app.ui.export_job_editor import ExportJobEditor
from app.ui.export_jobs_pages import ExportJobsEditorPage, ExportJobsTilesPage


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
        self._current_editor_id: str | None = None
        self._build_ui()
        self._jobs = ExportJobsCollectionController(
            config=self._config,
            parent=self,
            tiles_page=self._tiles_page,
            editor_page=self._editor_page,
            open_editor=self._show_editor,
            delete_job=self._on_tile_delete,
            emit_sync_completed=self.sync_completed.emit,
            emit_history_changed=self.history_changed.emit,
            emit_failure_alert=self.failure_alert.emit,
        )
        self._editors = self._jobs.editors()
        self._delete_controller = ExportJobsDeleteController(
            tiles_page=self._tiles_page,
            editor_page=self._editor_page,
            save_jobs=self._jobs.save_jobs,
            show_tiles=self._show_tiles,
            emit_history_changed=self.history_changed.emit,
            warn_running=lambda title, message: QMessageBox.warning(
                self,
                title,
                message,
            ),
            confirm_delete=self._confirm_delete,
        )
        self._jobs.load_jobs()

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

    def _add_new_job(self) -> None:
        self._jobs.add_new_job()

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
        self._jobs.sync_tiles_from_editors()

    @Slot()
    def _delete_current_editor(self) -> None:
        if self._current_editor_id is None:
            return
        self._on_tile_delete(self._current_editor_id)

    @Slot(str)
    def _run_job(self, job_id: str) -> None:
        self._jobs.run_job(job_id)

    @Slot(str)
    def _on_tile_delete(self, job_id: str) -> None:
        self._delete_controller.delete_job(
            job_id=job_id,
            editors=self._editors,
            current_editor_id=self._current_editor_id,
        )

    def _confirm_delete(self, job_name: str) -> bool:
        reply = QMessageBox.question(
            self,
            "Удалить выгрузку",
            f"Удалить выгрузку «{job_name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

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
