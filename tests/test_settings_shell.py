"""Tests for extracted SettingsWidget shell/composite view."""

from PySide6.QtCore import Qt

from app.ui.settings_app_panel import SettingsAppPanel
from app.ui.settings_shell import SettingsShell
from app.ui.settings_sql_panel import SettingsSqlPanel


def test_settings_shell_exposes_panels_and_buttons(qtbot) -> None:
    shell = SettingsShell("1.2.3")
    qtbot.addWidget(shell)

    assert isinstance(shell.sql_panel(), SettingsSqlPanel)
    assert isinstance(shell.app_panel(), SettingsAppPanel)
    assert shell.reset_button().text().strip() == "Сбросить"
    assert shell.save_button().text().strip() == "Сохранить"


def test_settings_shell_emits_bottom_action_signals(qtbot) -> None:
    shell = SettingsShell("1.2.3")
    qtbot.addWidget(shell)

    reset_requested = []
    save_requested = []
    shell.reset_requested.connect(lambda: reset_requested.append(True))
    shell.save_requested.connect(lambda: save_requested.append(True))

    qtbot.mouseClick(shell.reset_button(), Qt.MouseButton.LeftButton)
    qtbot.mouseClick(shell.save_button(), Qt.MouseButton.LeftButton)

    assert reset_requested == [True]
    assert save_requested == [True]
