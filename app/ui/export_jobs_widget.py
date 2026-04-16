# -*- coding: utf-8 -*-
"""ExportJobsWidget — list-detail export job manager (tiles + editor pages)."""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QMessageBox,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    ConfigManager,
    ExportJob,
)
from app.ui.export_job_editor import ExportJobEditor
from app.ui.export_job_tile import ExportJobTile
from app.ui.export_jobs_delete_controller import ExportJobsDeleteController
from app.ui.export_jobs_pages import ExportJobsEditorPage, ExportJobsTilesPage
from app.ui.export_jobs_store import (
    load_export_jobs,
    new_export_job,
    persist_export_jobs,
)


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
        self._delete_controller = ExportJobsDeleteController(
            tiles_page=self._tiles_page,
            editor_page=self._editor_page,
            save_jobs=self._save_jobs,
            show_tiles=self._show_tiles,
            emit_history_changed=self.history_changed.emit,
            warn_running=lambda title, message: QMessageBox.warning(
                self,
                title,
                message,
            ),
            confirm_delete=self._confirm_delete,
        )
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
