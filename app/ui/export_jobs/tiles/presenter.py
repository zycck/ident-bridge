"""Presentation helpers for ExportJobTile."""

from dataclasses import dataclass
from datetime import datetime
from collections.abc import Mapping

from app.export.run_store import ExportRunInfo
from app.ui.export_editor_runtime import format_short_user_error
from app.ui.export_jobs.status_summary import build_unfinished_run_status, latest_unfinished_run
from app.ui.formatters import format_duration_compact, format_relative_timestamp
from app.ui.theme import Theme


@dataclass(frozen=True, slots=True)
class ExportJobTileDisplay:
    name: str
    status_text: str
    status_color: str
    schedule_text: str


def build_export_job_tile_display(
    job: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> ExportJobTileDisplay:
    """Normalize ExportJob into a compact tile view model."""
    current = now or datetime.now()
    return ExportJobTileDisplay(
        name=job.get("name") or "Без названия",
        status_text=_build_status_text(job, current),
        status_color=_build_status_color(job),
        schedule_text=_build_schedule_text(job),
    )


def _build_status_text(job: Mapping[str, object], now: datetime) -> str:
    unfinished = _latest_unfinished_run(job)
    if unfinished is not None:
        _, text, _ = build_unfinished_run_status(unfinished, max_error_length=40)
        return text

    history = job.get("history") or []
    if not history:
        return "Ещё не запускалось"

    latest = history[0]
    if latest.get("ok"):
        ts_short = _format_short_ts(latest.get("ts", ""), now=now)
        duration_us = int(latest.get("duration_us") or 0)
        duration_suffix = (
            f" · {format_duration_compact(duration_us)}"
            if duration_us > 0
            else ""
        )
        return f"✓ {latest.get('rows', 0)} строк · {ts_short}{duration_suffix}"

    err = latest.get("err", "Ошибка")
    return f"✗ {format_short_user_error(err, max_length=40)}"


def _build_status_color(job: Mapping[str, object]) -> str:
    unfinished = _latest_unfinished_run(job)
    if unfinished is not None:
        _, _, color = build_unfinished_run_status(unfinished, max_error_length=40)
        return color

    history = job.get("history") or []
    if not history:
        return Theme.gray_500
    return Theme.success if history[0].get("ok") else Theme.error


def _latest_unfinished_run(job: Mapping[str, object]) -> ExportRunInfo | None:
    raw_runs = job.get("unfinished_runs") or []
    if not isinstance(raw_runs, list):
        return None
    return latest_unfinished_run(raw_runs)


def _build_schedule_text(job: Mapping[str, object]) -> str:
    if not job.get("schedule_enabled"):
        return "Ручной запуск"
    mode = job.get("schedule_mode", "daily")
    value = job.get("schedule_value", "")
    if not value:
        return "Расписание не настроено"
    if mode == "daily":
        return f"Ежедневно в {value}"
    if mode == "hourly":
        return f"Каждые {value} ч"
    if mode == "minutely":
        return f"Каждые {value} мин"
    if mode == "secondly":
        return f"Каждые {value} с"
    return f"Расписание: {mode}"


def _format_short_ts(ts: str, *, now: datetime) -> str:
    # Tile uses lowercase labels and never shows a year suffix — the
    # display is already compact ("✓ 12 строк · вчера 14:32").
    return format_relative_timestamp(
        ts,
        now=now,
        today_label="сегодня",
        yesterday_label="вчера",
        include_year_on_other=False,
    )
