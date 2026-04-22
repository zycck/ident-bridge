"""Export jobs list/detail container."""

from typing import override

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from app.config import ConfigManager
from app.export.run_store import ExportRunStore
from app.ui.export_job_editor import ExportJobEditor  # re-exported for existing imports/tests
from app.ui.export_jobs_collection_controller import ExportJobsCollectionController
from app.ui.export_jobs_delete_controller import ExportJobsDeleteController
from app.ui.export_jobs_navigation_controller import ExportJobsNavigationController
from app.ui.export_jobs_pages import ExportJobsEditorPage, ExportJobsTilesPage


class ExportJobsWidget(QWidget):
    """Container for export jobs: list of tiles + detail editor pages."""

    sync_completed = Signal(object)
    history_changed = Signal()
    failure_alert = Signal(str, int)

    def __init__(
        self,
        config: ConfigManager,
        run_store: ExportRunStore | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._run_store = run_store or ExportRunStore()
        self._build_ui()
        self._jobs = ExportJobsCollectionController(
            config=self._config,
            run_store=self._run_store,
            parent=self,
            tiles_page=self._tiles_page,
            editor_page=self._editor_page,
            open_editor=self._open_editor,
            delete_job=self._on_tile_delete,
            emit_sync_completed=self.sync_completed.emit,
            emit_history_changed=self.history_changed.emit,
            emit_failure_alert=self.failure_alert.emit,
        )
        self._editors = self._jobs.editors()
        self._navigation = ExportJobsNavigationController(
            stack=self._stack,
            editor_page=self._editor_page,
            editors=self._editors,
            ensure_editor=self._jobs.ensure_editor,
            sync_tiles_from_editors=self._jobs.sync_tiles_from_editors,
        )
        self._delete_controller = ExportJobsDeleteController(
            tiles_page=self._tiles_page,
            editor_page=self._editor_page,
            save_jobs=self._jobs.save_jobs,
            show_tiles=self._show_tiles,
            emit_history_changed=self.history_changed.emit,
            warn_running=lambda title, message: QMessageBox.warning(self, title, message),
            confirm_delete=self._confirm_delete,
        )
        self._jobs.load_jobs()

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
        self._stack.addWidget(self._tiles_page)
        self._stack.addWidget(self._editor_page)

    def _add_new_job(self) -> None:
        self._jobs.add_new_job()

    @Slot(str)
    def _open_editor(self, job_id: str) -> None:
        self._navigation.show_editor(job_id)

    @Slot(str)
    def _show_editor(self, job_id: str) -> None:
        self._open_editor(job_id)

    @Slot()
    def _show_tiles(self) -> None:
        self._navigation.show_tiles()

    @Slot()
    def _delete_current_editor(self) -> None:
        if self._navigation.current_editor_id is None:
            return
        self._on_tile_delete(self._navigation.current_editor_id)

    @Slot(str)
    def _run_job(self, job_id: str) -> None:
        self._jobs.run_job(job_id)

    @Slot(str)
    def _on_tile_delete(self, job_id: str) -> None:
        self._delete_controller.delete_job(
            job_id=job_id,
            editors=self._editors,
            jobs_by_id=self._jobs.jobs_by_id(),
            current_editor_id=self._navigation.current_editor_id,
        )

    def _confirm_delete(self, job_name: str) -> bool:
        reply = QMessageBox.question(
            self,
            "Удалить выгрузку",
            f"Удалить выгрузку «{job_name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    def stop_all_schedulers(self) -> None:
        for editor in self._editors.values():
            editor.stop_scheduler()

    def flush_pending_save(self) -> None:
        self._jobs.flush_pending_save()

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        self._jobs.flush_pending_save()
        self._navigation.stop_all_editors()
        super().closeEvent(event)
