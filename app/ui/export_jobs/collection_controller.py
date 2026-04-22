"""Collection/persistence controller for ExportJobsWidget."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QMessageBox, QFrame, QScrollArea, QVBoxLayout, QWidget

from app.config import ConfigManager, ExportJob
from app.core.constants import DEBOUNCE_SAVE_MS
from app.export.run_store import ExportRunStore
from app.ui.export_job_editor import ExportJobEditor
from app.ui.export_job_tile import ExportJobTile
from app.ui.export_jobs_store import (
    find_duplicate_export_target,
    load_export_jobs,
    new_export_job,
    persist_export_jobs,
)
from app.ui.theme import Theme


class ExportJobsCollectionController:
    """Owns export-job creation, persistence, and tile/editor wiring."""

    def __init__(
        self,
        *,
        config: ConfigManager,
        run_store: ExportRunStore | None = None,
        parent: QWidget,
        tiles_page,
        editor_page,
        open_editor: Callable[[str], None],
        delete_job: Callable[[str], None],
        emit_sync_completed: Callable[[object], None],
        emit_history_changed: Callable[[], None],
        emit_failure_alert: Callable[[str, int], None],
        warn_duplicate_target: Callable[[str, str], None] | None = None,
        tile_factory: type[QWidget] = ExportJobTile,
        editor_factory: type[Any] = ExportJobEditor,
    ) -> None:
        self._config = config
        self._run_store = run_store
        self._parent = parent
        self._tiles_page = tiles_page
        self._editor_page = editor_page
        self._open_editor = open_editor
        self._delete_job = delete_job
        self._emit_sync_completed = emit_sync_completed
        self._emit_history_changed = emit_history_changed
        self._emit_failure_alert = emit_failure_alert
        self._warn_duplicate_target = (
            warn_duplicate_target
            if warn_duplicate_target is not None
            else lambda title, message: QMessageBox.warning(self._parent, title, message)
        )
        self._tile_factory = tile_factory
        self._editor_factory = editor_factory
        self._editors: dict[str, Any] = {}
        self._save_timer = QTimer(parent)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(DEBOUNCE_SAVE_MS)
        self._save_timer.timeout.connect(self.save_jobs)

    def editors(self) -> dict[str, Any]:
        return self._editors

    def load_jobs(self) -> None:
        for job in load_export_jobs(self._config, self._run_store):
            self._register_job(job)
        self._tiles_page.refresh_empty()
        self._tiles_page.reflow_tiles()

    def queue_save_jobs(self) -> None:
        self._save_timer.start()

    def flush_pending_save(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.save_jobs()

    def save_jobs(self) -> None:
        self._save_timer.stop()
        jobs = [editor.to_job() for editor in self._editors.values()]
        duplicate = find_duplicate_export_target(jobs)
        if duplicate is not None:
            first_job_id, second_job_id, webhook_url, sheet_name = duplicate
            job_by_id = {job["id"]: job for job in jobs}
            first_name = str(job_by_id.get(first_job_id, {}).get("name", "") or "без названия")
            second_name = str(job_by_id.get(second_job_id, {}).get("name", "") or "без названия")
            self._warn_duplicate_target(
                "Дубликат выгрузки",
                (
                    f"Нельзя использовать один и тот же адрес обработки и лист в нескольких выгрузках.\n"
                    f"Адрес: {webhook_url}\n"
                    f"Лист: {sheet_name}\n"
                    f"Уже есть: «{first_name}» и «{second_name}»."
                ),
            )
            return

        persist_export_jobs(self._config, jobs)
        self.sync_tiles_from_editors(refresh_journal=False)

    def add_new_job(self) -> None:
        job = new_export_job()
        self._register_job(job)
        self.save_jobs()
        self._tiles_page.refresh_empty()
        self._tiles_page.reflow_tiles()
        self._open_editor(job["id"])

    def run_job(self, job_id: str) -> bool:
        editor = self._editors.get(job_id)
        if editor is None:
            return False
        return bool(editor.start_export())

    def sync_tiles_from_editors(self, *, refresh_journal: bool = True) -> None:
        tiles_by_id = {
            tile.job_id(): tile
            for tile in self._tiles_page.tiles()
        }
        for editor in self._editors.values():
            job = editor.to_job()
            if refresh_journal and self._run_store is not None:
                job["history"] = self._run_store.list_job_history(job["id"])
                job["unfinished_runs"] = self._run_store.list_unfinished_runs(job_id=job["id"])
            tile = tiles_by_id.get(job.get("id"))
            if tile is not None:
                tile.update_from_job(job)

    def _register_job(self, job: ExportJob) -> None:
        self._add_tile(job)
        self._editors[job["id"]] = self._create_editor(job)

    def _add_tile(self, job: ExportJob) -> None:
        tile = self._tile_factory(job, self._parent)
        tile.open_requested.connect(self._open_editor)
        tile.run_requested.connect(self.run_job)
        tile.delete_requested.connect(self._delete_job)
        self._tiles_page.add_tile(tile)

    def _create_editor(self, job: ExportJob):
        try:
            if self._run_store is not None:
                editor = self._editor_factory(job, self._config, self._run_store, self._parent)
            else:
                raise TypeError
        except TypeError:
            editor = self._editor_factory(job, self._config, self._parent)
        editor.changed.connect(lambda _job: self.queue_save_jobs())
        editor.history_changed.connect(self._emit_history_changed)
        editor.sync_completed.connect(self._emit_sync_completed)
        editor.failure_alert.connect(self._emit_failure_alert)
        runtime_signal = getattr(editor, "runtime_state_changed", None)
        if runtime_signal is not None:
            runtime_signal.connect(
                lambda kind, text, running, current_job_id=job["id"]: self._sync_tile_runtime_state(
                    current_job_id,
                    kind=kind,
                    text=text,
                    running=running,
                )
            )

        container = QWidget()
        container.setStyleSheet(f"background: {Theme.surface_tinted};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)
        layout.addWidget(editor, stretch=1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: {Theme.surface_tinted}; border: none; }}"
        )
        scroll.setWidget(container)

        self._editor_page.add_editor(job.get("id", ""), scroll)
        return editor

    def _sync_tile_runtime_state(self, job_id: str, *, kind: str, text: str, running: bool) -> None:
        for tile in self._tiles_page.tiles():
            tile_job_id = getattr(tile, "job_id", lambda: None)()
            if tile_job_id != job_id:
                continue
            set_runtime_state = getattr(tile, "set_runtime_state", None)
            if callable(set_runtime_state):
                set_runtime_state(kind=kind, text=text, running=running)
            return
