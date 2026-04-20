"""Tests for extracted export execution orchestration."""

from datetime import datetime, timezone

from app.config import SyncResult
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

    def start_worker(worker, on_finished, on_error, on_progress):
        started.append((worker, on_finished, on_error, on_progress))

    controller = ExportExecutionController(
        runtime=ExportEditorRuntimeState(),
        load_config=lambda: {"sql_instance": "server\\SQLEXPRESS"},
        build_job=lambda: {"id": "job-1", "name": "Nightly"},
        create_worker=lambda cfg, job: ("worker", cfg, job),
        start_worker=start_worker,
        set_run_enabled=lambda enabled: events.append(("run_enabled", enabled)),
        set_progress_text=lambda text: events.append(("progress", text)),
        set_status=lambda kind, text: events.append(("status", kind, text)),
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
    assert events[:3] == [
        ("run_enabled", False),
        ("progress", "Запуск…"),
        ("status", "running", "Запуск…"),
    ]


def test_progress_and_success_restore_ui_and_emit_sync() -> None:
    controller, events, started = _controller()
    controller.start_manual()

    _, on_finished, _, on_progress = started[0]
    on_progress(2, "Отправка данных... 2/5")
    on_finished(_success_result())

    assert ("progress", "Отправка данных... 2/5") in events
    assert ("status", "running", "Отправка данных... 2/5") in events
    assert ("run_enabled", True) in events
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
