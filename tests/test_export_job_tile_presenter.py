"""Tests for extracted export job tile presenter."""

from datetime import datetime

import pytest

from app.export.run_store import ExportRunInfo
from app.ui.export_editor_runtime import format_short_user_error
from app.ui.export_job_tile_presenter import _build_schedule_text, build_export_job_tile_display
from app.ui.theme import Theme


def test_export_job_tile_presenter_handles_empty_job() -> None:
    display = build_export_job_tile_display({}, now=datetime(2026, 4, 16, 15, 30, 0))

    assert display.name == "Без названия"
    assert display.status_text == "Ещё не запускалось"
    assert display.schedule_text == "Ручной запуск"


def test_export_job_tile_presenter_formats_success_status_and_daily_schedule() -> None:
    display = build_export_job_tile_display(
        {
            "name": "Nightly",
            "schedule_enabled": True,
            "schedule_mode": "daily",
            "schedule_value": "03:00",
            "history": [
                {
                    "ts": "2026-04-16 12:00:00",
                    "ok": True,
                    "rows": 12,
                    "duration_us": 7_500,
                },
            ],
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.name == "Nightly"
    assert display.status_text == "✓ 12 строк · сегодня 12:00:00 · 7.5 мс"
    assert display.schedule_text == "Ежедневно в 03:00"


def test_export_job_tile_presenter_formats_error_status_and_interval_modes() -> None:
    display = build_export_job_tile_display(
        {
            "schedule_enabled": True,
            "schedule_mode": "minutely",
            "schedule_value": "5",
            "history": [
                {
                    "ts": "2026-04-15 09:15:00",
                    "ok": False,
                    "err": "Ошибка публикации в Apps Script.\n\nTraceback (most recent call last):\n  File \"worker.py\", line 1",
                },
            ],
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.status_text == "✗ Ошибка публикации в Apps Script."
    assert display.schedule_text == "Каждые 5 мин"


def test_export_job_tile_presenter_truncates_long_short_error_for_tile_only() -> None:
    msg = "Не удалось доставить данные: 2/5 чанков. Подробности в Debug. И еще немного текста."
    display = build_export_job_tile_display(
        {
            "history": [
                {"ts": "2026-04-15 09:15:00", "ok": False, "err": msg},
            ],
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.status_text == f"✗ {format_short_user_error(msg, max_length=40)}"


def test_export_job_tile_presenter_prefers_unfinished_sqlite_run_status() -> None:
    display = build_export_job_tile_display(
        {
            "history": [
                {"ts": "2026-04-15 09:15:00", "ok": True, "rows": 99},
            ],
            "unfinished_runs": [
                ExportRunInfo(
                    run_id="run-1",
                    job_id="job-1",
                    job_name="Nightly",
                    webhook_url="https://example.test",
                    sheet_name="Exports",
                    source_id="job-1",
                    write_mode="replace_all",
                    export_date="2026-04-21",
                    total_chunks=5,
                    total_rows=100,
                    delivered_chunks=2,
                    delivered_rows=40,
                    status="running",
                    trigger="manual",
                    created_at="2026-04-21T09:00:00+00:00",
                    updated_at="2026-04-21T09:05:00+00:00",
                    started_at="2026-04-21T09:00:10+00:00",
                    finished_at=None,
                    last_error="",
                    sql_duration_us=0,
                    total_duration_us=0,
                    supersedes_run_id=None,
                )
            ],
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.status_text == "Оборвано · 2/5 чанков"
    assert display.status_color == Theme.warning


@pytest.mark.parametrize(
    ("job", "expected"),
    [
        (
            {"schedule_enabled": True, "schedule_mode": "daily", "schedule_value": "03:00"},
            "Ежедневно в 03:00",
        ),
        (
            {"schedule_enabled": True, "schedule_mode": "hourly", "schedule_value": "4"},
            "Каждые 4 ч",
        ),
        (
            {"schedule_enabled": True, "schedule_mode": "minutely", "schedule_value": "5"},
            "Каждые 5 мин",
        ),
        (
            {"schedule_enabled": True, "schedule_mode": "secondly", "schedule_value": "30"},
            "Каждые 30 с",
        ),
        (
            {"schedule_enabled": True, "schedule_mode": "weeklyish", "schedule_value": "7"},
            "Расписание: weeklyish",
        ),
    ],
)
def test_build_schedule_text_formats_known_and_unknown_modes(
    job: dict[str, object],
    expected: str,
) -> None:
    assert _build_schedule_text(job) == expected


def test_export_job_tile_presenter_handles_unknown_schedule_modes() -> None:
    display = build_export_job_tile_display(
        {
            "schedule_enabled": True,
            "schedule_mode": "weeklyish",
            "schedule_value": "7",
        },
        now=datetime(2026, 4, 16, 15, 30, 0),
    )

    assert display.schedule_text == "Расписание: weeklyish"
