"""Tests for extracted settings app-side effects controller."""

from PySide6.QtWidgets import QCheckBox

from app.ui.settings_actions import StartupToggleResult
from app.ui.settings_app_controller import SettingsAppController


def test_app_controller_reverts_checkbox_and_warns_on_startup_failure(qtbot) -> None:
    startup_check = QCheckBox()
    qtbot.addWidget(startup_check)
    startup_check.setChecked(True)
    warnings: list[tuple[str, str]] = []

    controller = SettingsAppController(
        startup_check=startup_check,
        update_coordinator=type("U", (), {"check": lambda self: True})(),
        apply_startup_toggle_fn=lambda checked: StartupToggleResult(
            ok=False,
            error="registry error",
            actual_enabled=not checked,
        ),
        warn_fn=lambda _parent, title, message: warnings.append((title, message)),
    )

    controller.handle_startup_toggled(True)

    assert startup_check.isChecked() is False
    assert warnings == [("Автозапуск", "Не удалось изменить запись в реестре:\nregistry error")]


def test_app_controller_passes_update_check_through() -> None:
    calls: list[bool] = []

    class _UpdateCoordinator:
        def check(self) -> bool:
            calls.append(True)
            return True

    controller = SettingsAppController(
        startup_check=QCheckBox(),
        update_coordinator=_UpdateCoordinator(),
    )

    assert controller.check_update() is True
    assert calls == [True]
