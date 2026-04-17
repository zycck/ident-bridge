"""Presentation helpers for ExportJobTile."""

from dataclasses import dataclass
from datetime import datetime

from app.config import ExportJob
from app.ui.formatters import format_relative_timestamp
from app.ui.theme import Theme


@dataclass(frozen=True, slots=True)
class ExportJobTileDisplay:
    name: str
    status_text: str
    status_color: str
    schedule_text: str


def build_export_job_tile_display(
    job: ExportJob,
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


def _build_status_text(job: ExportJob, now: datetime) -> str:
    history = job.get("history") or []
    if not history:
        return "Ещё не запускалось"

    latest = history[0]
    if latest.get("ok"):
        ts_short = _format_short_ts(latest.get("ts", ""), now=now)
        return f"✓ {latest.get('rows', 0)} строк · {ts_short}"

    err = latest.get("err", "Ошибка")
    return f"✗ {err[:40]}"


def _build_status_color(job: ExportJob) -> str:
    history = job.get("history") or []
    if not history:
        return Theme.gray_500
    return Theme.success if history[0].get("ok") else Theme.error


def _build_schedule_text(job: ExportJob) -> str:
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
