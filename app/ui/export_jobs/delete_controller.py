"""Deletion flow extracted from ExportJobsWidget."""


def _safe_signal_disconnect(signal) -> None:
    try:
        signal.disconnect()
    except (TypeError, RuntimeError):
        pass


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
        jobs_by_id: dict,
        current_editor_id: str | None,
    ) -> bool:
        editor = editors.get(job_id)
        if editor is not None and getattr(editor, "_running", False):
            self._warn_running(
                "\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0430 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0435\u0442\u0441\u044f",
                "\u0414\u043e\u0436\u0434\u0438\u0442\u0435\u0441\u044c \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0438\u044f \u0432\u044b\u0433\u0440\u0443\u0437\u043a\u0438 \u043f\u0435\u0440\u0435\u0434 \u0443\u0434\u0430\u043b\u0435\u043d\u0438\u0435\u043c.",
            )
            return False

        fallback_name = "\u0431\u0435\u0437 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u044f"
        name = fallback_name
        if editor is not None:
            name = editor.to_job().get("name") or fallback_name
        elif job_id in jobs_by_id:
            name = jobs_by_id[job_id].get("name") or fallback_name
        if not self._confirm_delete(name):
            return False

        if editor is not None:
            editor.stop_scheduler()
            editor.stop_timers()
            scroll = self._editor_page.remove_editor(job_id)
            if scroll is not None:
                scroll.deleteLater()
            for signal_name in (
                "changed",
                "sync_completed",
                "history_changed",
                "failure_alert",
            ):
                signal = getattr(editor, signal_name, None)
                if signal is not None:
                    _safe_signal_disconnect(signal)
            editor.deleteLater()
            del editors[job_id]

        jobs_by_id.pop(job_id, None)

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
