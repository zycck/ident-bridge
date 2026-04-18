"""Tests for extracted HistoryRow presentation helpers."""

from datetime import datetime

from app.ui.history_row_presenter import build_history_row_display, format_history_timestamp


def test_format_history_timestamp_supports_today_yesterday_and_legacy_widths() -> None:
    now = datetime(2026, 4, 16, 15, 30, 0)

    assert format_history_timestamp("2026-04-16 12:00:00", now=now) == "Сегодня 12:00:00"
    assert format_history_timestamp("2026-04-15 08:15:00", now=now) == "Вчера 08:15:00"
    assert format_history_timestamp("2026-03-01 07:05:00", now=now) == "01.03 07:05:00"
    assert format_history_timestamp("2025-12-31 23:59:00", now=now) == "31.12.25 23:59:00"
    assert format_history_timestamp("2026-04-16 12:00", now=now) == "Сегодня 12:00:00"


def test_build_history_row_display_maps_legacy_trigger_and_success_status() -> None:
    display = build_history_row_display(
        {
            "ts": "2026-04-16 12:00:00",
            "trigger": "auto",
            "ok": True,
            "rows": 5,
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.icon_name == "clock"
    assert display.trigger_label == "Авто"
    assert display.timestamp_text == "Сегодня 12:00:00"
    assert display.status_text == "✓  5 строк"
    assert display.status_tooltip == ""


def test_build_history_row_display_falls_back_to_manual_and_preserves_error_tooltip() -> None:
    display = build_history_row_display(
        {
            "ts": "2026-04-14 09:15:00",
            "trigger": "unexpected",
            "ok": False,
            "err": "Ошибка публикации в Apps Script.\n\nTraceback (most recent call last):\n  File \"worker.py\", line 1",
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.icon_name == "mouse-pointer-click"
    assert display.trigger_label == "Вручную"
    assert display.status_text == "✗ Ошибка публикации в Apps Script."
    assert display.status_tooltip == "Ошибка публикации в Apps Script."


def test_build_history_row_display_keeps_full_short_error_in_tooltip() -> None:
    msg = "Не удалось доставить данные: 2/5 чанков. Подробности в Debug."
    display = build_history_row_display(
        {
            "ts": "2026-04-14 09:15:00",
            "trigger": "manual",
            "ok": False,
            "err": msg,
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.status_text.startswith("✗ Не удалось доставить данные")
    assert display.status_tooltip == msg
