"""Startup/update side-effects controller for SettingsWidget."""

from collections.abc import Callable

from PySide6.QtCore import QObject, QSignalBlocker, Slot
from PySide6.QtWidgets import QCheckBox, QMessageBox

from app.ui.settings_actions import SettingsUpdateCoordinator, StartupToggleResult, apply_startup_toggle


class SettingsAppController(QObject):
    """Owns non-visual app-side actions for the settings screen."""

    def __init__(
        self,
        *,
        startup_check: QCheckBox,
        update_coordinator: SettingsUpdateCoordinator,
        apply_startup_toggle_fn: Callable[[bool], StartupToggleResult] = apply_startup_toggle,
        warn_fn: Callable[[object, str, str], object] = QMessageBox.warning,
    ) -> None:
        super().__init__(startup_check)
        self._startup_check = startup_check
        self._update_coordinator = update_coordinator
        self._apply_startup_toggle = apply_startup_toggle_fn
        self._warn = warn_fn

    @Slot(bool)
    def handle_startup_toggled(self, checked: bool) -> StartupToggleResult:
        result = self._apply_startup_toggle(checked)
        if not result.ok:
            with QSignalBlocker(self._startup_check):
                self._startup_check.setChecked(not checked)
            self._warn(
                self.parent(),
                "Автозапуск",
                f"Не удалось изменить запись в реестре:\n{result.error}",
            )
        return result

    def check_update(self) -> bool:
        return self._update_coordinator.check()
