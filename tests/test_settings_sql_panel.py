"""Tests for extracted settings SQL section panel."""

from PySide6.QtCore import Qt

from app.ui.settings_sql_panel import SettingsSqlPanel


def test_settings_sql_panel_exposes_expected_widgets(qtbot) -> None:
    panel = SettingsSqlPanel()
    qtbot.addWidget(panel)

    assert panel.instance_combo().isEditable() is True
    assert panel.database_combo().count() == 0
    assert panel.login_edit().placeholderText() == "sa"
    assert panel.password_edit().placeholderText() == "••••••"


def test_settings_sql_panel_button_signals_fire(qtbot) -> None:
    panel = SettingsSqlPanel()
    qtbot.addWidget(panel)

    with qtbot.waitSignal(panel.scan_requested, timeout=1000):
        qtbot.mouseClick(panel.scan_button(), Qt.MouseButton.LeftButton)

    with qtbot.waitSignal(panel.refresh_databases_requested, timeout=1000):
        qtbot.mouseClick(panel.refresh_databases_button(), Qt.MouseButton.LeftButton)

    with qtbot.waitSignal(panel.test_connection_requested, timeout=1000):
        qtbot.mouseClick(panel.test_connection_button(), Qt.MouseButton.LeftButton)


def test_settings_sql_panel_accessors_return_stable_widget_instances(qtbot) -> None:
    panel = SettingsSqlPanel()
    qtbot.addWidget(panel)

    assert panel.instance_combo() is panel.instance_combo()
    assert panel.database_combo() is panel.database_combo()
    assert panel.conn_status() is panel.conn_status()
