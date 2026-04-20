"""Shared core presentation helpers."""

__all__ = ["format_duration_compact"]


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
