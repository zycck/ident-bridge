# -*- coding: utf-8 -*-
"""Tests for extracted SettingsWidget signal/delegate coordinator."""

from app.ui.settings_shell import SettingsShell
from app.ui.settings_widget_controller import SettingsWidgetController


class _FakeFormController:
    def __init__(self) -> None:
        self.load_calls = 0
        self.save_calls = 0
        self.db_indices: list[int] = []
        self.auto_save_calls = 0

    def load_fields(self) -> None:
        self.load_calls += 1

    def save(self) -> None:
        self.save_calls += 1

    def handle_database_changed(self, idx: int) -> None:
        self.db_indices.append(idx)

    def auto_save(self) -> bool:
        self.auto_save_calls += 1
        return True


class _FakeSqlController:
    def __init__(self) -> None:
        self.scan_calls = 0
        self.instance_indices: list[int] = []
        self.refresh_calls = 0
        self.test_calls = 0

    def scan_instances(self) -> bool:
        self.scan_calls += 1
        return True

    def handle_instance_changed(self, idx: int) -> bool:
        self.instance_indices.append(idx)
        return True

    def refresh_databases(self) -> bool:
        self.refresh_calls += 1
        return True

    def test_connection(self) -> bool:
        self.test_calls += 1
        return True


class _FakeAppController:
    def __init__(self) -> None:
        self.startup_toggles: list[bool] = []
        self.check_calls = 0

    def handle_startup_toggled(self, checked: bool):
        self.startup_toggles.append(checked)

    def check_update(self) -> bool:
        self.check_calls += 1
        return True


def test_settings_widget_controller_wires_form_actions_and_autosave(qtbot) -> None:
    shell = SettingsShell("3.14.4")
    qtbot.addWidget(shell)
    shell.sql_panel().database_combo().addItems(["placeholder", "db"])

    form = _FakeFormController()
    sql = _FakeSqlController()
    app = _FakeAppController()
    infos: list[tuple[str, str]] = []
    controller = SettingsWidgetController(
        shell=shell,
        form_controller=form,
        sql_controller=sql,
        app_controller=app,
        info_fn=lambda _parent, title, message: infos.append((title, message)),
    )

    controller.wire()
    controller.load_initial_state()
    shell.reset_requested.emit()
    shell.save_requested.emit()
    shell.sql_panel().database_combo().setCurrentIndex(1)
    shell.sql_panel().login_edit().editingFinished.emit()
    shell.sql_panel().password_edit().editingFinished.emit()
    shell.app_panel().auto_update_check().setChecked(True)

    assert form.load_calls == 2
    assert form.save_calls == 1
    assert form.db_indices == [1]
    assert form.auto_save_calls >= 3
    assert infos == [("Сохранено", "Настройки сохранены.")]


def test_settings_widget_controller_wires_sql_actions(qtbot) -> None:
    shell = SettingsShell("3.14.4")
    qtbot.addWidget(shell)
    shell.sql_panel().instance_combo().addItems(["placeholder", "server\\SQLEXPRESS"])
    sql = _FakeSqlController()

    controller = SettingsWidgetController(
        shell=shell,
        form_controller=_FakeFormController(),
        sql_controller=sql,
        app_controller=_FakeAppController(),
    )

    controller.wire()
    shell.sql_panel().scan_requested.emit()
    shell.sql_panel().refresh_databases_requested.emit()
    shell.sql_panel().test_connection_requested.emit()
    shell.sql_panel().instance_combo().setCurrentIndex(1)

    assert sql.scan_calls == 1
    assert sql.refresh_calls == 1
    assert sql.test_calls == 1
    assert sql.instance_indices == [1]


def test_settings_widget_controller_wires_app_actions(qtbot) -> None:
    shell = SettingsShell("3.14.4")
    qtbot.addWidget(shell)
    app = _FakeAppController()

    controller = SettingsWidgetController(
        shell=shell,
        form_controller=_FakeFormController(),
        sql_controller=_FakeSqlController(),
        app_controller=app,
    )

    controller.wire()
    shell.app_panel().startup_check().setChecked(True)
    shell.app_panel().check_update_requested.emit()

    assert app.startup_toggles == [True]
    assert app.check_calls == 1
