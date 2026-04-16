# -*- coding: utf-8 -*-
"""Collection/persistence controller for ExportJobsWidget."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from app.config import ConfigManager, ExportJob
from app.ui.export_job_editor import ExportJobEditor
from app.ui.export_job_tile import ExportJobTile
from app.ui.export_jobs_store import load_export_jobs, new_export_job, persist_export_jobs


class ExportJobsCollectionController:
    """Owns export-job creation, persistence, and tile/editor wiring."""

    def __init__(
        self,
        *,
        config: ConfigManager,
        parent: QWidget,
        tiles_page,
        editor_page,
        open_editor: Callable[[str], None],
        delete_job: Callable[[str], None],
        emit_sync_completed: Callable[[object], None],
        emit_history_changed: Callable[[], None],
        emit_failure_alert: Callable[[str, int], None],
        tile_factory: type[QWidget] = ExportJobTile,
        editor_factory: type[Any] = ExportJobEditor,
    ) -> None:
        self._config = config
        self._parent = parent
        self._tiles_page = tiles_page
        self._editor_page = editor_page
        self._open_editor = open_editor
        self._delete_job = delete_job
        self._emit_sync_completed = emit_sync_completed
        self._emit_history_changed = emit_history_changed
        self._emit_failure_alert = emit_failure_alert
        self._tile_factory = tile_factory
        self._editor_factory = editor_factory
        self._editors: dict[str, Any] = {}

    def editors(self) -> dict[str, Any]:
        return self._editors

    def load_jobs(self) -> None:
        for job in load_export_jobs(self._config):
            self._register_job(job)
        self._tiles_page.refresh_empty()
        self._tiles_page.reflow_tiles()

    def save_jobs(self) -> None:
        persist_export_jobs(
            self._config,
            [editor.to_job() for editor in self._editors.values()],
        )
        self.sync_tiles_from_editors()

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
        editor.start_export()
        return True

    def sync_tiles_from_editors(self) -> None:
        tiles_by_id = {
            tile.job_id(): tile
            for tile in self._tiles_page.tiles()
        }
        for editor in self._editors.values():
            job = editor.to_job()
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
        editor = self._editor_factory(job, self._config, self._parent)
        editor.changed.connect(lambda _job: self.save_jobs())
        editor.history_changed.connect(self._emit_history_changed)
        editor.history_changed.connect(self.save_jobs)
        editor.sync_completed.connect(self._emit_sync_completed)
        editor.failure_alert.connect(self._emit_failure_alert)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)
        layout.addWidget(editor, stretch=1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(container)

        self._editor_page.add_editor(job.get("id", ""), scroll)
        return editor
