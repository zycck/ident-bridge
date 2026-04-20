"""Presentation helpers for HistoryRow."""

from dataclasses import dataclass
from datetime import datetime

from app.config import ExportHistoryEntry, TriggerType
from app.ui.export_editor_runtime import (
    format_short_user_error,
    normalize_short_user_error,
)
from app.ui.formatters import format_duration_compact, format_relative_timestamp
from app.ui.theme import Theme


@dataclass(frozen=True, slots=True)
class HistoryRowDisplay:
    icon_name: str
    accent_color: str
    trigger_label: str
    timestamp_text: str
    status_text: str
    status_color: str
    status_tooltip: str


_TRIGGER_META: dict[TriggerType, tuple[str, str, str]] = {
    TriggerType.MANUAL: ("mouse-pointer-click", Theme.info, "Вручную"),
    TriggerType.SCHEDULED: ("clock", Theme.primary_500, "Авто"),
    TriggerType.TEST: ("flask-conical", Theme.gray_500, "Тест"),
}


def format_history_timestamp(ts: str, *, now: datetime | None = None) -> str:
    """Return a friendly timestamp label for a persisted history entry."""
    return format_relative_timestamp(
        ts,
        now=now,
        today_label="Сегодня",
        yesterday_label="Вчера",
        include_year_on_other=True,
    )


def build_history_row_display(
    entry: ExportHistoryEntry,
    *,
    now: datetime | None = None,
) -> HistoryRowDisplay:
    """Normalize ExportHistoryEntry into a view-model for HistoryRow."""
    trigger = _coerce_trigger(entry.get("trigger", "manual"))
    icon_name, accent, label = _TRIGGER_META[trigger]
    ok = bool(entry.get("ok"))

    if ok:
        rows = entry.get("rows", 0)
        duration_us = int(entry.get("duration_us") or 0)
        duration_suffix = (
            f" · {format_duration_compact(duration_us)}"
            if duration_us > 0
            else ""
        )
        status_text = f"✓  {rows} строк{duration_suffix}"
        status_color = Theme.success
        status_tooltip = ""
    else:
        err = entry.get("err", "Ошибка")
        status_text = f"✗ {format_short_user_error(err, max_length=55)}"
        status_color = Theme.error
        status_tooltip = normalize_short_user_error(err)

    return HistoryRowDisplay(
        icon_name=icon_name,
        accent_color=accent,
        trigger_label=label,
        timestamp_text=format_history_timestamp(entry.get("ts", ""), now=now),
        status_text=status_text,
        status_color=status_color,
        status_tooltip=status_tooltip,
    )


def _coerce_trigger(trigger_str: str) -> TriggerType:
    if trigger_str == "auto":
        trigger_str = "scheduled"
    try:
        return TriggerType(trigger_str)
    except ValueError:
        return TriggerType.MANUAL
