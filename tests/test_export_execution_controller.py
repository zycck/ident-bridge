"""Tests for extracted export execution orchestration."""

from datetime import datetime, timezone

from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.config import SyncResult
from app.export.run_store import ExportRunInfo
from app.ui.export_editor_runtime import ExportEditorRuntimeState
from app.ui.export_execution_controller import ExportExecutionController


def _success_result() -> SyncResult:
    return SyncResult(
        success=True,
        rows_synced=9,
        error=None,
        timestamp=datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
        duration_us=15_500,
        sql_duration_us=9_250,
    )


def _controller():
    events: list[tuple] = []
    started: list[tuple] = []
    history_snapshot = [{"ts": "2026-01-01 12:00:00", "ok": True, "rows": 1}]
    unfinished_snapshot = [
        ExportRunInfo(
            run_id="run-open",
            job_id="job-1",
            job_name="Nightly",
            webhook_url="https://script.google.com/macros/s/demo/exec",
            sheet_name="Exports",
            source_id="job-1",
            write_mode="replace_all",
            export_date="2026-01-01",
            total_chunks=3,
            total_rows=9,
            delivered_chunks=1,
            delivered_rows=3,
            status="failed",
            trigger="manual",
            created_at="2026-01-01T12:00:00+00:00",
            updated_at="2026-01-01T12:01:00+00:00",
            started_at="2026-01-01T12:00:05+00:00",
            finished_at=None,
            last_error="Ошибка",
            sql_duration_us=0,
            total_duration_us=0,
            supersedes_run_id=None,
        )
    ]

    def start_worker(worker, on_finished, on_error, on_progress):
        started.append((worker, on_finished, on_error, on_progress))

    controller = ExportExecutionController(
        runtime=ExportEditorRuntimeState(),
        load_config=lambda: {"sql_instance": "server\\SQLEXPRESS"},
        build_job=lambda: {"id": "job-1", "name": "Nightly"},
        create_worker=lambda cfg, job, trigger: ("worker", cfg, job, trigger),
        start_worker=start_worker,
        set_run_enabled=lambda enabled: events.append(("run_enabled", enabled)),
        set_run_busy=lambda busy: events.append(("run_busy", busy)),
        set_progress_text=lambda text: events.append(("progress", text)),
        set_status=lambda kind, text: events.append(("status", kind, text)),
        set_history=lambda history: events.append(("history_set", len(history))),
        emit_runtime_state_changed=lambda kind, text, running: events.append(("runtime", kind, text, running)),
        load_history=lambda: history_snapshot,
        set_unfinished=lambda runs: events.append(("unfinished_set", [run.run_id for run in runs])),
        load_unfinished=lambda: unfinished_snapshot,
        add_history_entry=lambda entry: events.append(("history", entry)),
        emit_sync_completed=lambda result: events.append(("sync", result.rows_synced)),
        emit_failure_alert=lambda name, count: events.append(("alert", name, count)),
        now_func=lambda: datetime(2026, 1, 1, 12, 0, 0),
    )
    return controller, events, started


def test_start_manual_is_idempotent_while_running() -> None:
    controller, events, started = _controller()

    assert controller.start_manual() is True
    assert controller.start_manual() is False

    assert len(started) == 1
    assert events[:5] == [
        ("run_enabled", False),
        ("run_busy", True),
        ("progress", "Запуск…"),
        ("status", "running", "Запуск…"),
        ("runtime", "running", "Запуск…", True),
    ]


def test_start_scheduled_is_idempotent_while_running() -> None:
    controller, _events, started = _controller()

    assert controller.start_scheduled() is True
    assert controller.start_scheduled() is False

    assert len(started) == 1
    assert started[0][0][3] == "scheduled"


def test_progress_and_success_restore_ui_and_emit_sync() -> None:
    controller, events, started = _controller()
    controller.start_manual()

    _, on_finished, _, on_progress = started[0]
    on_progress(2, "Отправка данных... 2/5")
    on_finished(_success_result())

    assert ("progress", "Отправка данных... 2/5") in events
    assert ("status", "running", "Отправка данных... 2/5") in events
    assert ("run_busy", False) in events
    assert ("run_enabled", True) in events
    assert ("runtime", "ok", "✓ 9 строк · 12:05:00 · 15.5 мс", False) in events
    assert ("sync", 9) in events
    history_events = [item for item in events if item[0] == "history"]
    assert history_events[-1][1]["ok"] is True
    assert history_events[-1][1]["duration_us"] == 15_500
    assert history_events[-1][1]["sql_duration_us"] == 9_250


def test_error_emits_alert_on_threshold() -> None:
    controller, events, started = _controller()

    for _ in range(3):
        controller.start_manual()
        _, _, on_error, _ = started[-1]
        on_error("Ошибка отправки данных.\n\nTraceback (most recent call last):\n  File \"worker.py\", line 1")

    assert ("alert", "Nightly", 3) in events
    assert ("run_busy", False) in events
    history_events = [item for item in events if item[0] == "history"]
    assert history_events[-1][1]["ok"] is False
    assert history_events[-1][1]["err"] == "Ошибка отправки данных."
    assert controller.consecutive_failures == 3


def test_record_test_completed_creates_test_history_entry() -> None:
    controller, events, _ = _controller()

    controller.record_test_completed(ok=True, rows=4, err="")

    history_event = [item for item in events if item[0] == "history"][-1]
    assert history_event[1]["trigger"] == "test"
    assert history_event[1]["rows"] == 4
    assert history_event[1]["duration_us"] == 0
    assert history_event[1]["sql_duration_us"] == 0


def test_finished_run_refreshes_history_and_unfinished_snapshots() -> None:
    controller, events, started = _controller()
    controller.start_manual()

    _, on_finished, _, _ = started[0]
    on_finished(_success_result())

    assert ("history_set", 1) in events
    assert ("unfinished_set", ["run-open"]) in events


class _ThreadedSignalWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    error = Signal(str)

    @Slot()
    def run(self) -> None:
        self.progress.emit(2, "Отправка данных... 1/1")
        self.finished.emit(_success_result())


def test_threaded_export_callbacks_run_on_gui_thread(qapp_session, qtbot) -> None:
    gui_thread = qapp_session.thread()
    progress_threads: list[bool] = []
    finish_threads: list[bool] = []
    done: list[bool] = []

    controller = ExportExecutionController(
        runtime=ExportEditorRuntimeState(),
        load_config=lambda: {"sql_instance": "server\\SQLEXPRESS"},
        build_job=lambda: {"id": "job-1", "name": "Nightly"},
        create_worker=lambda cfg, job, trigger: ("worker", cfg, job, trigger),
        start_worker=lambda *args, **kwargs: None,
        set_run_enabled=lambda _enabled: finish_threads.append(QThread.currentThread() is gui_thread),
        set_run_busy=lambda _busy: finish_threads.append(QThread.currentThread() is gui_thread),
        set_progress_text=lambda _text: progress_threads.append(QThread.currentThread() is gui_thread),
        set_status=lambda _kind, _text: finish_threads.append(QThread.currentThread() is gui_thread),
        set_history=lambda _history: finish_threads.append(QThread.currentThread() is gui_thread),
        set_unfinished=lambda _runs: finish_threads.append(QThread.currentThread() is gui_thread),
        emit_runtime_state_changed=lambda *_args: finish_threads.append(QThread.currentThread() is gui_thread),
        load_history=lambda: [],
        load_unfinished=lambda: [],
        add_history_entry=lambda _entry: finish_threads.append(QThread.currentThread() is gui_thread),
        emit_sync_completed=lambda _result: finish_threads.append(QThread.currentThread() is gui_thread),
        emit_failure_alert=lambda _name, _count: finish_threads.append(QThread.currentThread() is gui_thread),
        now_func=lambda: datetime(2026, 1, 1, 12, 0, 0),
    )

    worker = _ThreadedSignalWorker()
    thread = QThread()
    worker.moveToThread(thread)
    worker.progress.connect(controller.on_progress)
    worker.finished.connect(controller.on_finished)
    worker.error.connect(controller.on_error)
    worker.finished.connect(lambda *_args: done.append(True))
    worker.finished.connect(thread.quit)
    worker.error.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.started.connect(worker.run)

    thread.start()
    qtbot.waitUntil(lambda: bool(progress_threads) and bool(finish_threads) and bool(done), timeout=3000)
    qtbot.wait(50)

    assert progress_threads
    assert all(progress_threads)
    assert all(finish_threads)
