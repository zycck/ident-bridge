# -*- coding: utf-8 -*-
"""Navigation/lifecycle controller for ExportJobsWidget."""


class ExportJobsNavigationController:
    """Owns list/detail routing and shutdown cleanup for export jobs."""

    def __init__(
        self,
        *,
        stack,
        editor_page,
        editors: dict,
        sync_tiles_from_editors,
    ) -> None:
        self._stack = stack
        self._editor_page = editor_page
        self._editors = editors
        self._sync_tiles_from_editors = sync_tiles_from_editors
        self._current_editor_id: str | None = None

    @property
    def current_editor_id(self) -> str | None:
        return self._current_editor_id

    def show_editor(self, job_id: str) -> bool:
        if self._editors.get(job_id) is None:
            return False
        if not self._editor_page.show_editor(job_id):
            return False
        self._current_editor_id = job_id
        self._stack.setCurrentIndex(1)
        return True

    def show_tiles(self) -> None:
        self._current_editor_id = None
        self._stack.setCurrentIndex(0)
        self._sync_tiles_from_editors()

    def stop_all_editors(self) -> None:
        for editor in self._editors.values():
            editor.stop_scheduler()
            editor.stop_timers()
