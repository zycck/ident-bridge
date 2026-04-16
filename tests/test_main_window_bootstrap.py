# -*- coding: utf-8 -*-
"""Tests for extracted MainWindow startup/bootstrap wiring."""

from PySide6.QtCore import QObject, Signal, Qt

from app.ui.main_window_bootstrap import MainWindowBootstrapController


class _FakeApp(QObject):
    aboutToQuit = Signal()


class _FakeConfig:
    def __init__(self, auto_update_check: bool) -> None:
        self._auto_update_check = auto_update_check

    def get(self, key: str):
        if key == "auto_update_check":
            return self._auto_update_check
        raise KeyError(key)


class _FakeShortcut(QObject):
    activated = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.contexts: list[Qt.ShortcutContext] = []

    def setContext(self, context: Qt.ShortcutContext) -> None:
        self.contexts.append(context)


def test_bootstrap_wires_shortcut_cleanup_hook_and_update(qtbot) -> None:
    app = _FakeApp()
    toggles: list[bool] = []
    cleanups: list[bool] = []
    updates: list[bool] = []
    installed: list[bool] = []
    created_shortcuts: list[_FakeShortcut] = []

    def shortcut_factory(_sequence, _parent):
        shortcut = _FakeShortcut()
        created_shortcuts.append(shortcut)
        return shortcut

    controller = MainWindowBootstrapController(
        window=QObject(),
        config=_FakeConfig(auto_update_check=True),
        toggle_debug_window=lambda: toggles.append(True),
        cleanup=lambda: cleanups.append(True),
        run_update_check=lambda: updates.append(True),
        install_exception_hook=lambda: installed.append(True),
        app_instance=app,
        shortcut_factory=shortcut_factory,
    )

    controller.wire()
    created_shortcuts[0].activated.emit()
    app.aboutToQuit.emit()

    assert installed == [True]
    assert updates == [True]
    assert toggles == [True]
    assert cleanups == [True]
    assert created_shortcuts[0].contexts == [Qt.ShortcutContext.ApplicationShortcut]


def test_bootstrap_skips_update_when_disabled() -> None:
    updates: list[bool] = []

    controller = MainWindowBootstrapController(
        window=QObject(),
        config=_FakeConfig(auto_update_check=False),
        toggle_debug_window=lambda: None,
        cleanup=lambda: None,
        run_update_check=lambda: updates.append(True),
        install_exception_hook=lambda: None,
        app_instance=_FakeApp(),
        shortcut_factory=lambda _sequence, _parent: _FakeShortcut(),
    )

    controller.wire()

    assert updates == []
