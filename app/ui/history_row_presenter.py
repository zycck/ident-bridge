# -*- coding: utf-8 -*-
"""Presentation helpers for HistoryRow."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import ExportHistoryEntry, TriggerType
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
    if not ts or len(ts) < 16:
        return ts

    parsed = None
    for fmt, length in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
        if len(ts) >= length:
            try:
                parsed = datetime.strptime(ts[:length], fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return ts

    current = now or datetime.now()
    today = current.date()
    time_text = parsed.strftime("%H:%M:%S")
    if parsed.date() == today:
        return f"Сегодня {time_text}"
    if parsed.date() == today - timedelta(days=1):
        return f"Вчера {time_text}"
    if parsed.year == current.year:
        return f"{parsed.strftime('%d.%m')} {time_text}"
    return f"{parsed.strftime('%d.%m.%y')} {time_text}"


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
        status_text = f"✓  {rows} строк"
        status_color = Theme.success
        status_tooltip = ""
    else:
        err = entry.get("err", "Ошибка")
        status_text = f"✗  {err[:55]}"
        status_color = Theme.error
        status_tooltip = err

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
