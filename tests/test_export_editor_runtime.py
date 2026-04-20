"""Tests for extracted export editor runtime state."""

from datetime import datetime, timezone

from app.config import SyncResult, TriggerType
from app.ui.export_editor_runtime import ExportEditorRuntimeState


def _success_result() -> SyncResult:
    return SyncResult(
        success=True,
        rows_synced=7,
        error=None,
        timestamp=datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc),
        duration_us=12_345,
        sql_duration_us=7_500,
    )


def test_runtime_state_builds_success_status_and_history_entry() -> None:
    state = ExportEditorRuntimeState()

    state.mark_manual_trigger()
    state.begin_run()
    status_kind, status_text, entry = state.on_success(_success_result())

    assert status_kind == "ok"
    assert status_text == "✓ 7 строк · 12:05:00 · 12.3 мс"
    assert entry == {
        "ts": "2026-01-01 12:05:00",
        "trigger": TriggerType.MANUAL.value,
        "ok": True,
        "rows": 7,
        "err": "",
        "duration_us": 12_345,
        "sql_duration_us": 7_500,
    }
    assert state.consecutive_failures == 0


def test_runtime_state_counts_failures_and_alert_threshold() -> None:
    state = ExportEditorRuntimeState()

    alerts = []
    for _ in range(3):
        state.mark_manual_trigger()
        state.begin_run()
        payload = state.on_error(
            "Ошибка отправки данных.\n\nTraceback (most recent call last):\n  File \"worker.py\", line 1",
            now=datetime(2026, 1, 1, 12, 0, 0),
            alert_threshold=3,
        )
        alerts.append(payload.alert_count)

    assert alerts == [None, None, 3]
    assert state.consecutive_failures == 3
    assert payload.entry["trigger"] == TriggerType.MANUAL.value
    assert payload.entry["ok"] is False
    assert payload.entry["err"] == "Ошибка отправки данных."
    assert payload.status_text == "✗ Ошибка отправки данных."


def test_runtime_state_normalizes_traceback_like_error_to_last_meaningful_line() -> None:
    state = ExportEditorRuntimeState()
    state.mark_manual_trigger()
    state.begin_run()

    payload = state.on_error(
        "Traceback (most recent call last):\n  File \"x\", line 1\nValueError: broken ack",
        now=datetime(2026, 1, 1, 12, 0, 0),
        alert_threshold=3,
    )

    assert payload.status_text == "✗ ValueError: broken ack"
    assert payload.entry["err"] == "ValueError: broken ack"


def test_runtime_state_restores_status_from_latest_history_entry() -> None:
    ok_kind, ok_text = ExportEditorRuntimeState.status_from_latest_entry(
        {
            "ts": "2026-04-16 09:10:11",
            "trigger": TriggerType.MANUAL.value,
            "ok": True,
            "rows": 3,
            "err": "",
            "duration_us": 9_000,
        }
    )
    err_kind, err_text = ExportEditorRuntimeState.status_from_latest_entry(
        {
            "ts": "2026-04-16 09:10:11",
            "trigger": TriggerType.MANUAL.value,
            "ok": False,
            "rows": 0,
            "err": "Ошибка отправки данных.\n\nTraceback (most recent call last):\n  File \"worker.py\", line 1",
        }
    )

    assert (ok_kind, ok_text) == ("ok", "✓ 3 строк · 09:10:11 · 9 мс")
    assert (err_kind, err_text) == ("error", "✗ Ошибка отправки данных.")
