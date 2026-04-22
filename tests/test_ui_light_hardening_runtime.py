from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QMenu

from app.ui.dialogs.debug.window import DebugWindow
from app.ui.error_dialog import ErrorDialog
from app.ui.theme import Theme
from app.ui.widgets import apply_light_window_palette, style_menu_popup


def _name(widget, role: QPalette.ColorRole) -> str:
    return widget.palette().color(role).name().lower()


def test_shared_light_helpers_force_light_palette(qtbot) -> None:
    menu = QMenu()
    qtbot.addWidget(menu)
    style_menu_popup(menu)

    assert Theme.surface.lower() in menu.styleSheet().lower()
    assert _name(menu, QPalette.ColorRole.Window) == Theme.surface.lower()
    assert bool(menu.windowFlags() & Qt.WindowType.NoDropShadowWindowHint)

    apply_light_window_palette(menu)
    assert _name(menu, QPalette.ColorRole.Text) == Theme.gray_900.lower()
    disabled_text = menu.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name().lower()
    disabled_button_text = menu.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name().lower()
    assert disabled_text == Theme.gray_500.lower()
    assert disabled_button_text == Theme.gray_500.lower()


def test_debug_window_uses_light_log_surface_and_light_combo_popup(
    qtbot,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.ui.debug_window.DebugWindowLogController.connect", lambda self: None)
    monkeypatch.setattr("app.ui.debug_window.DebugWindowLogController.disconnect", lambda self: None)

    window = DebugWindow()
    qtbot.addWidget(window)

    log_style = window._log.styleSheet().lower()
    assert Theme.surface.lower() in log_style
    assert Theme.gray_900.lower() in log_style
    assert "#0b0d12" not in log_style
    assert Theme.surface.lower() in window._level_filter.view().styleSheet().lower()
    assert _name(window, QPalette.ColorRole.Window) in {
        Theme.surface.lower(),
        Theme.surface_tinted.lower(),
    }


def test_error_dialog_uses_light_window_hardening(qtbot) -> None:
    dialog = ErrorDialog(RuntimeError("boom"))
    qtbot.addWidget(dialog)

    assert _name(dialog, QPalette.ColorRole.Window) in {
        Theme.surface.lower(),
        Theme.surface_tinted.lower(),
    }
    assert dialog.styleSheet()
