"""Execution/orchestration helper for ExportJobEditor."""

from collections.abc import Callable
from datetime import datetime
import time
from typing import Any

from PySide6.QtCore import QObject, Slot

from app.config import ExportHistoryEntry, SyncResult
from app.ui.export_editor_runtime import ExportEditorRuntimeState


class ExportExecutionController(QObject):
    """Owns worker/test-run orchestration for ExportJobEditor."""

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        runtime: ExportEditorRuntimeState,
        load_config: Callable[[], dict[str, Any]],
        build_job: Callable[[], dict[str, Any]],
        create_worker: Callable[[dict[str, Any], dict[str, Any]], Any],
        start_worker: Callable[[Any, Callable[[object], None], Callable[[str], None], Callable[[int, str], None]], None],
        set_run_enabled: Callable[[bool], None],
        set_run_busy: Callable[[bool], None],
        set_progress_text: Callable[[str], None],
        set_status: Callable[[str, str], None],
        set_history: Callable[[list[ExportHistoryEntry]], None] | None = None,
        set_unfinished: Callable[[list[object]], None] | None = None,
        emit_runtime_state_changed: Callable[[str, str, bool], None],
        load_history: Callable[[], list[ExportHistoryEntry]] | None = None,
        load_unfinished: Callable[[], list[object]] | None = None,
        record_history_entry: Callable[[ExportHistoryEntry], None] | None = None,
        record_error_entry: Callable[[ExportHistoryEntry], None] | None = None,
        add_history_entry: Callable[[ExportHistoryEntry], None] | None = None,
        emit_sync_completed: Callable[[SyncResult], None],
        emit_failure_alert: Callable[[str, int], None],
        now_func: Callable[[], datetime] = datetime.now,
        failure_alert_threshold: int = 3,
    ) -> None:
        super().__init__(parent)
        self._runtime = runtime
        self._load_config = load_config
        self._build_job = build_job
        self._create_worker = create_worker
        self._start_worker = start_worker
        self._set_run_enabled = set_run_enabled
        self._set_run_busy = set_run_busy
        self._set_progress_text = set_progress_text
        self._set_status = set_status
        self._set_history = set_history or (lambda _history: None)
        self._set_unfinished = set_unfinished or (lambda _runs: None)
        self._emit_runtime_state_changed = emit_runtime_state_changed
        self._load_history = load_history or (lambda: [])
        self._load_unfinished = load_unfinished or (lambda: [])
        self._record_history_entry = record_history_entry or add_history_entry or (lambda _entry: None)
        self._record_error_entry = record_error_entry or add_history_entry or self._record_history_entry
        self._emit_sync_completed = emit_sync_completed
        self._emit_failure_alert = emit_failure_alert
        self._now = now_func
        self._failure_alert_threshold = failure_alert_threshold
        self._running = False
        self._run_started_ns = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def consecutive_failures(self) -> int:
        return self._runtime.consecutive_failures

    def start_manual(self) -> bool:
        self._runtime.mark_manual_trigger()
        return self._start()

    def start_scheduled(self) -> bool:
        self._runtime.mark_scheduled_trigger()
        return self._start()

    def _start(self) -> bool:
        if self._running:
            return False
        self._running = True
        self._run_started_ns = time.perf_counter_ns()
        status_kind, status_text = self._runtime.begin_run()
        self._set_run_enabled(False)
        self._set_run_busy(True)
        self._set_progress_text("Запуск…")
        self._set_status(status_kind, status_text)
        self._emit_runtime_state_changed(status_kind, status_text, True)

        worker = self._create_worker(self._load_config(), self._build_job())
        self._start_worker(worker, self.on_finished, self.on_error, self.on_progress)
        return True

    @Slot(int, str)
    def on_progress(self, _step: int, description: str) -> None:
        self._set_progress_text(description)
        self._set_status("running", description)
        self._emit_runtime_state_changed("running", description, True)

    @Slot(object)
    def on_finished(self, result: SyncResult) -> None:
        self._running = False
        self._run_started_ns = 0
        self._set_run_busy(False)
        self._set_run_enabled(True)
        self._set_progress_text("")

        if not result.success:
            self._set_history(self._load_history())
            self._set_unfinished(self._load_unfinished())
            return

        status_kind, status_text, entry = self._runtime.on_success(result)
        if not result.journaled:
            self._record_history_entry(entry)
        self._set_status(status_kind, status_text)
        self._emit_runtime_state_changed(status_kind, status_text, False)
        self._set_history(self._load_history())
        self._set_unfinished(self._load_unfinished())
        self._emit_sync_completed(result)

    @Slot(str)
    def on_error(self, msg: str) -> None:
        duration_us = 0
        if self._run_started_ns:
            duration_us = max(0, (time.perf_counter_ns() - self._run_started_ns) // 1_000)
        self._running = False
        self._run_started_ns = 0
        update = self._runtime.on_error(
            msg,
            now=self._now(),
            alert_threshold=self._failure_alert_threshold,
            duration_us=duration_us,
        )
        self._set_run_busy(False)
        self._set_run_enabled(True)
        self._set_progress_text("")
        self._set_status(update.status_kind, update.status_text)
        self._emit_runtime_state_changed(update.status_kind, update.status_text, False)
        self._record_error_entry(update.entry)
        if update.alert_count is not None:
            name = self._build_job().get("name") or "Без названия"
            self._emit_failure_alert(name, update.alert_count)

    def record_test_completed(
        self,
        *,
        ok: bool,
        rows: int,
        err: str,
        duration_us: int = 0,
    ) -> None:
        entry = self._runtime.build_test_entry(
            ok=ok,
            rows=rows,
            err=err,
            now=self._now(),
            duration_us=duration_us,
        )
        self._record_history_entry(entry)
        self._set_history(self._load_history())
