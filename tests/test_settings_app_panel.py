# -*- coding: utf-8 -*-
"""Tests for extracted settings application section panel."""

from PySide6.QtCore import Qt

from app.ui.settings_app_panel import SettingsAppPanel


def test_settings_app_panel_exposes_expected_version_and_controls(qtbot) -> None:
    panel = SettingsAppPanel("3.14.4")
    qtbot.addWidget(panel)

    assert panel.version_text() == "Версия: 3.14.4"
    assert panel.startup_check().text() == "Запускать с Windows"
    assert panel.auto_update_check().text() == "Проверять обновления при запуске"


def test_settings_app_panel_emits_startup_toggle_and_update_request(qtbot) -> None:
    panel = SettingsAppPanel("3.14.4")
    qtbot.addWidget(panel)

    with qtbot.waitSignal(panel.startup_toggled, timeout=1000) as startup_blocker:
        panel.startup_check().setChecked(True)
    assert startup_blocker.args == [True]

    with qtbot.waitSignal(panel.check_update_requested, timeout=1000):
        qtbot.mouseClick(panel.check_update_button(), Qt.MouseButton.LeftButton)
