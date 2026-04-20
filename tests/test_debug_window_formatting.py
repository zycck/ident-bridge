"""Tests for debug window log formatting helpers."""

from app.ui.debug_window_formatting import filter_log_lines, get_log_level


def test_log_level_filter_thresholds_and_all_mode() -> None:
    lines = [
        "12:00:00 [DEBUG] demo: debug",
        "12:00:01 [INFO] demo: info",
        "12:00:02 [WARNING] demo: warning",
        "12:00:03 [ERROR] demo: error",
        "12:00:04 [CRITICAL] demo: critical",
        "plain text",
    ]

    assert get_log_level(lines[0]) == "DEBUG"
    assert get_log_level(lines[-1]) is None
    assert filter_log_lines(lines, None) == lines
    assert filter_log_lines(lines, "WARNING") == [lines[2]]
    assert filter_log_lines(lines, "ERROR") == [lines[3]]
    assert filter_log_lines(lines, "INFO") == [lines[1]]
