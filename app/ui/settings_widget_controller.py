# -*- coding: utf-8 -*-
"""Signal/delegate coordinator for SettingsWidget."""

from collections.abc import Callable

from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QMessageBox

from app.ui.settings_shell import SettingsShell


class SettingsWidgetController(QObject):
    """Owns signal wiring between the settings shell and extracted controllers."""

    def __init__(
        self,
        *,
        shell: SettingsShell,
        form_controller,
        sql_controller,
        app_controller,
        info_fn: Callable[[object, str, str], object] = QMessageBox.information,
    ) -> None:
        super().__init__(shell)
        self._shell = shell
        self._form = form_controller
        self._sql = sql_controller
        self._app = app_controller
        self._info = info_fn

    def wire(self) -> None:
        self._shell.reset_requested.connect(self.reset)
        self._shell.save_requested.connect(self.save)

        sql_panel = self._shell.sql_panel()
        sql_panel.instance_combo().currentIndexChanged.connect(self._on_instance_changed)
        sql_panel.scan_requested.connect(self._scan_instances)
        sql_panel.refresh_databases_requested.connect(self._refresh_databases)
        sql_panel.test_connection_requested.connect(self._test_connection)
        sql_panel.database_combo().currentIndexChanged.connect(self._on_db_changed)
        sql_panel.login_edit().editingFinished.connect(self._auto_save)
        sql_panel.password_edit().editingFinished.connect(self._auto_save)
        if sql_panel.instance_combo().lineEdit() is not None:
            sql_panel.instance_combo().lineEdit().editingFinished.connect(self._auto_save)

        app_panel = self._shell.app_panel()
        app_panel.auto_update_check().toggled.connect(self._auto_save)
        app_panel.startup_toggled.connect(self._on_startup_toggled)
        app_panel.check_update_requested.connect(self._check_update)

    def load_initial_state(self) -> None:
        self._form.load_fields()

    @Slot()
    def reset(self) -> None:
        self._form.load_fields()

    @Slot()
    def save(self) -> None:
        self._form.save()
        self._info(self.parent(), "Сохранено", "Настройки сохранены.")

    @Slot(int)
    def _on_db_changed(self, idx: int) -> None:
        self._form.handle_database_changed(idx)

    def _auto_save(self) -> bool:
        return self._form.auto_save()

    def _scan_instances(self) -> bool:
        return self._sql.scan_instances()

    @Slot(int)
    def _on_instance_changed(self, idx: int) -> bool:
        return self._sql.handle_instance_changed(idx)

    def _refresh_databases(self) -> bool:
        return self._sql.refresh_databases()

    def _test_connection(self) -> bool:
        return self._sql.test_connection()

    @Slot(bool)
    def _on_startup_toggled(self, checked: bool) -> None:
        self._app.handle_startup_toggled(checked)

    def _check_update(self) -> bool:
        return self._app.check_update()
