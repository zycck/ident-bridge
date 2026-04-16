"""Helpers for formatting debug log lines in the floating log window."""

import re

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
_LINE_RE = re.compile(r"^(\d{2}:\d{2}:\d{2}) \[(\w+)\] ([^:]+): (.*)$")


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_log_line_html(text: str) -> str:
    """Convert a plain log line into HTML with colored spans."""
    match = _LINE_RE.match(text)
    if not match:
        return f'<span style="color:{_STYLE_DEFAULT}">{_esc(text)}</span>'

    timestamp, level, logger, message = match.groups()
    level_color = _LEVEL_COLORS.get(level, "#A1A1AA")
    weight = "700" if level == "CRITICAL" else "600"

    return (
        f'<span style="color:{_STYLE_TIMESTAMP}">{_esc(timestamp)}</span> '
        f'<span style="color:{level_color}; font-weight:{weight}">[{_esc(level)}]</span> '
        f'<span style="color:{_STYLE_LOGGER}">{_esc(logger)}</span>'
        f'<span style="color:{_STYLE_TIMESTAMP}">:</span> '
        f'<span style="color:{_STYLE_DEFAULT}">{_esc(message)}</span>'
    )
