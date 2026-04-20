"""Shared presentation-layer formatters."""

from datetime import datetime, timedelta

from app.core.formatters import format_duration_compact

__all__ = ["format_duration_compact", "format_relative_timestamp"]


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
      parsed - no exceptions bubble out of a UI formatter.
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
