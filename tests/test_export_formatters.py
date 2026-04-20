"""Tests for shared export-related presentation formatters."""

import pytest

from app.core.formatters import format_duration_compact
from app.ui.formatters import format_duration_compact as ui_format_duration_compact


@pytest.mark.parametrize(
    ("duration_us", "expected"),
    [
        (0, "0 мкс"),
        (850, "850 мкс"),
        (7_500, "7.5 мс"),
        (12_345, "12.3 мс"),
        (1_250_000, "1.2 с"),
        (65_000_000, "1м 05с"),
        (3_660_000_000, "1ч 01м"),
    ],
)
def test_format_duration_compact_uses_reasonable_units(
    duration_us: int,
    expected: str,
) -> None:
    assert format_duration_compact(duration_us) == expected


def test_ui_formatters_reexports_duration_helper() -> None:
    assert ui_format_duration_compact is format_duration_compact
