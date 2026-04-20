"""Bridge/services layer for ExportJobEditor."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import ExportHistoryEntry, ExportJob
from app.core.scheduler import schedule_mode_to_raw
from app.ui.threading import run_worker

if TYPE_CHECKING:
    from app.ui.test_run_dialog import TestRunDialog


class ExportJobEditorBridge:
    """Owns payload serialization and external service wiring for the editor."""

    def __init__(
        self,
        *,
        owner,
        shell,
        job_id: str,
        run_worker_fn: Callable[..., object] = run_worker,
        test_dialog_factory: type["TestRunDialog"] | None = None,
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
            gas_options={
                "sheet_name": self._shell.gas_sheet_name(),
            },
            schedule_enabled=self._shell.schedule_enabled(),
            schedule_mode=schedule_mode_to_raw(self._shell.schedule_mode()),
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

    def create_test_dialog(self, cfg: dict[str, Any], sql: str) -> "TestRunDialog":
        dialog_factory = self._test_dialog_factory
        if dialog_factory is None:
            from app.ui.test_run_dialog import TestRunDialog

            dialog_factory = TestRunDialog
        return dialog_factory(
            cfg,
            initial_sql=sql,
            auto_run=bool(sql),
            parent=self._owner,
        )
