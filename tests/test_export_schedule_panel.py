# -*- coding: utf-8 -*-
"""Tests for extracted export schedule panel helpers."""

from app.core.scheduler import schedule_value_is_valid
from app.ui.export_schedule_panel import ExportSchedulePanel


def test_schedule_value_validation_covers_supported_modes() -> None:
    assert schedule_value_is_valid("daily", "08:30") is True
    assert schedule_value_is_valid("hourly", "2") is True
    assert schedule_value_is_valid("minutely", "15") is True
    assert schedule_value_is_valid("secondly", "10") is True
    assert schedule_value_is_valid("daily", "bad") is False
    assert schedule_value_is_valid("hourly", "0") is False
    assert schedule_value_is_valid("unknown", "1") is False


def test_schedule_panel_roundtrip(qtbot) -> None:
    panel = ExportSchedulePanel()
    qtbot.addWidget(panel)

    panel.set_schedule(True, "minutely", "5")

    assert panel.schedule_enabled() is True
    assert panel.schedule_mode() == "minutely"
    assert panel.schedule_value() == "5"
    assert panel._value_edit.placeholderText() == "N минут"


def test_schedule_panel_updates_placeholder_on_mode_change(qtbot) -> None:
    panel = ExportSchedulePanel()
    qtbot.addWidget(panel)

    panel._mode_combo.setCurrentIndex(3)

    assert panel._value_edit.placeholderText() == "N секунд"
