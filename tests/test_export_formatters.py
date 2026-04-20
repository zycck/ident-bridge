"""Tests for shared export-related presentation formatters."""

from app.ui.formatters import format_duration_compact


def test_format_duration_compact_uses_reasonable_units() -> None:
    assert format_duration_compact(850) == "850 мкс"
    assert format_duration_compact(7_500) == "7.5 мс"
    assert format_duration_compact(12_345) == "12.3 мс"
    assert format_duration_compact(1_250_000) == "1.2 с"
    assert format_duration_compact(65_000_000) == "1м 05с"
