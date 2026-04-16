# -*- coding: utf-8 -*-
"""Startup/bootstrap wiring extracted from MainWindow."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.error_dialog import install_global_handler


class MainWindowBootstrapController(QObject):
    """Owns startup wiring that should stay out of MainWindow shell code."""

    def __init__(
        self,
        *,
        window: QWidget,
        config,
        toggle_debug_window: Callable[[], None],
        cleanup: Callable[[], None],
        run_update_check: Callable[[], None],
        install_exception_hook: Callable[[], None] = install_global_handler,
        app_instance: Any | None = None,
        shortcut_factory: Callable[[QKeySequence, QWidget], Any] | None = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._config = config
        self._toggle_debug_window = toggle_debug_window
        self._cleanup = cleanup
        self._run_update_check = run_update_check
        self._install_exception_hook = install_exception_hook
        self._app_instance = app_instance
        self._shortcut_factory = shortcut_factory or QShortcut
        self._debug_shortcut: Any | None = None

    def wire(self) -> None:
        self._install_exception_hook()
        self._wire_shortcut()
        app = self._app_instance or QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._cleanup)
        if self._config.get("auto_update_check"):
            self._run_update_check()

    def _wire_shortcut(self) -> None:
        shortcut = self._shortcut_factory(QKeySequence("Ctrl+D"), self._window)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(self._toggle_debug_window)
        self._debug_shortcut = shortcut
