"""Bridge/services layer for ExportJobEditor."""

from collections.abc import Callable
from typing import Any

from app.config import ExportHistoryEntry, ExportJob
from app.ui.test_run_dialog import TestRunDialog
from app.ui.threading import run_worker


class ExportJobEditorBridge:
    """Owns payload serialization and external service wiring for the editor."""

    def __init__(
        self,
        *,
        owner,
        shell,
        job_id: str,
        run_worker_fn: Callable[..., object] = run_worker,
        test_dialog_factory: type[TestRunDialog] = TestRunDialog,
    ) -> None:
        self._owner = owner
        self._shell = shell
        self._job_id = job_id
        self._run_worker = run_worker_fn
        self._test_dialog_factory = test_dialog_factory

    def job_id(self) -> str:
        return self._job_id

    def build_job(self) -> ExportJob:
        return ExportJob(
            id=self._job_id,
            name=self._shell.job_name(),
            sql_query=self._shell.sql_text(),
            webhook_url=self._shell.webhook_url(),
            schedule_enabled=self._shell.schedule_enabled(),
            schedule_mode=self._shell.schedule_mode(),
            schedule_value=self._shell.schedule_value(),
            history=self._shell.history(),
        )

    def start_worker(
        self,
        worker: Any,
        on_finished,
        on_error,
        on_progress,
    ) -> None:
        worker.progress.connect(on_progress)
        self._run_worker(
            self._owner,
            worker,
            pin_attr="_worker",
            on_finished=on_finished,
            on_error=on_error,
        )

    def add_history_entry(self, entry: ExportHistoryEntry) -> None:
        self._shell.prepend_history_entry(entry)

    def create_test_dialog(self, cfg: dict[str, Any], sql: str) -> TestRunDialog:
        return self._test_dialog_factory(
            cfg,
            initial_sql=sql,
            auto_run=bool(sql),
            parent=self._owner,
        )
