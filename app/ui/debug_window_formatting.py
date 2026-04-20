"""Helpers for formatting debug log lines in the floating log window."""

import re
from collections.abc import Iterable

_STYLE_DEFAULT = "#D4D4D8"
_STYLE_TIMESTAMP = "#52525B"
_STYLE_LOGGER = "#A78BFA"
_LEVEL_COLORS: dict[str, str] = {
    "DEBUG": "#71717A",
    "INFO": "#22D3EE",
    "WARNING": "#FBBF24",
    "ERROR": "#F87171",
    "CRITICAL": "#EF4444",
}
_LEVEL_RANK: dict[str, int] = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}
_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{2}:\d{2}:\d{2}) \[(?P<level>\w+)\] (?P<logger>[^:]+): (?P<message>.*)$"
)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_log_level(text: str) -> str | None:
    """Return the structured log level from a formatted line, if present."""
    match = _LINE_RE.match(text)
    if not match:
        return None
    level = match.group("level")
    return level if level in _LEVEL_RANK else None


def filter_log_lines(lines: Iterable[str], selected_level: str | None) -> list[str]:
    """Filter formatted log lines by exact level match."""
    if selected_level is None:
        return list(lines)

    filtered: list[str] = []
    for line in lines:
        level = get_log_level(line)
        if level == selected_level:
            filtered.append(line)
    return filtered


def format_log_line_html(text: str) -> str:
    """Convert a plain log line into HTML with colored spans."""
    match = _LINE_RE.match(text)
    if not match:
        return f'<span style="color:{_STYLE_DEFAULT}">{_esc(text)}</span>'

    timestamp = match.group("timestamp")
    level = match.group("level")
    logger = match.group("logger")
    message = match.group("message")
    level_color = _LEVEL_COLORS.get(level, "#A1A1AA")
    weight = "700" if level == "CRITICAL" else "600"

    return (
        f'<span style="color:{_STYLE_TIMESTAMP}">{_esc(timestamp)}</span> '
        f'<span style="color:{level_color}; font-weight:{weight}">[{_esc(level)}]</span> '
        f'<span style="color:{_STYLE_LOGGER}">{_esc(logger)}</span>'
        f'<span style="color:{_STYLE_TIMESTAMP}">:</span> '
        f'<span style="color:{_STYLE_DEFAULT}">{_esc(message)}</span>'
    )


__all__ = ["filter_log_lines", "format_log_line_html", "get_log_level"]
