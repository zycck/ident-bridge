"""Shared presentation-layer formatters.

Keeps the "today/yesterday/date HH:MM:SS" logic in one place — the two
existing copies (ExportJobTilePresenter and HistoryRowPresenter) differed
only in label casing and whether two-digit-year suffixes should appear
for old entries. One function with keyword toggles now covers both.
"""

from __future__ import annotations

from datetime import datetime, timedelta

__all__ = ["format_duration_compact", "format_relative_timestamp"]


def _format_decimal(value: float, *, digits: int = 1) -> str:
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def format_duration_compact(duration_us: int) -> str:
    """Render a duration in microseconds using compact human units."""
    value = max(0, int(duration_us))
    if value < 1_000:
        return f"{value} мкс"

    milliseconds = value / 1_000
    if milliseconds < 100:
        return f"{_format_decimal(milliseconds)} мс"
    if milliseconds < 1_000:
        return f"{int(round(milliseconds))} мс"

    seconds = value / 1_000_000
    if seconds < 60:
        return f"{_format_decimal(seconds)} с"

    minutes, seconds_part = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes}м {seconds_part:02d}с"

    hours, minutes_part = divmod(minutes, 60)
    return f"{hours}ч {minutes_part:02d}м"


def format_relative_timestamp(
    ts: str,
    *,
    now: datetime | None = None,
    today_label: str = "Сегодня",
    yesterday_label: str = "Вчера",
    include_year_on_other: bool = True,
) -> str:
    """Render a persisted ``YYYY-MM-DD HH:MM[:SS]`` string in a friendly form.

    * ``"Сегодня HH:MM:SS"`` if ``ts`` is today (configurable casing).
    * ``"Вчера HH:MM:SS"`` if it's the previous day.
    * ``"DD.MM HH:MM:SS"`` for older dates in the same calendar year.
    * ``"DD.MM.YY HH:MM:SS"`` for older dates if
      ``include_year_on_other=True``; otherwise falls back to ``DD.MM``
      (previous behaviour in ExportJobTile).
    * Returns the original string unchanged when the input can't be
      parsed — no exceptions bubble out of a UI formatter.
    """
    if not ts or len(ts) < 16:
        return ts

    parsed: datetime | None = None
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
        return f"{today_label} {time_text}"
    if parsed.date() == today - timedelta(days=1):
        return f"{yesterday_label} {time_text}"
    if parsed.year == current.year or not include_year_on_other:
        return f"{parsed.strftime('%d.%m')} {time_text}"
    return f"{parsed.strftime('%d.%m.%y')} {time_text}"
