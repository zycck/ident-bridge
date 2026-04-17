"""Deletion flow extracted from ExportJobsWidget."""


class ExportJobsDeleteController:
    def __init__(
        self,
        *,
        tiles_page,
        editor_page,
        save_jobs,
        show_tiles,
        emit_history_changed,
        warn_running,
        confirm_delete,
    ) -> None:
        self._tiles_page = tiles_page
        self._editor_page = editor_page
        self._save_jobs = save_jobs
        self._show_tiles = show_tiles
        self._emit_history_changed = emit_history_changed
        self._warn_running = warn_running
        self._confirm_delete = confirm_delete

    def delete_job(
        self,
        *,
        job_id: str,
        editors: dict,
        current_editor_id: str | None,
    ) -> bool:
        editor = editors.get(job_id)
        if editor is not None and getattr(editor, "_running", False):
            self._warn_running(
                "Выгрузка выполняется",
                "Дождитесь завершения выгрузки перед удалением.",
            )
            return False

        name = "без названия"
        if editor is not None:
            name = editor.to_job().get("name") or "без названия"
        if not self._confirm_delete(name):
            return False

        if editor is not None:
            editor.stop_scheduler()
            editor.stop_timers()
            scroll = self._editor_page.remove_editor(job_id)
            if scroll is not None:
                scroll.deleteLater()
            editor.deleteLater()
            del editors[job_id]

        tile = self._tiles_page.remove_tile(job_id)
        if tile is not None:
            tile.deleteLater()

        if current_editor_id == job_id:
            self._show_tiles()

        self._save_jobs()
        self._tiles_page.refresh_empty()
        self._tiles_page.reflow_tiles()
        self._emit_history_changed()
        return True
