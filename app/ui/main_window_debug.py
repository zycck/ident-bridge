# -*- coding: utf-8 -*-
"""Lazy debug-window coordination extracted from MainWindow."""

from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget

from app.ui.debug_window import DebugWindow


class DebugWindowCoordinator(QObject):
    def __init__(
        self,
        parent: QObject | None = None,
        *,
        window_factory: Callable[[], QWidget] | None = None,
    ) -> None:
        super().__init__(parent)
        self._window_factory = window_factory or (lambda: DebugWindow(parent=None))
        self._window: QWidget | None = None

    @property
    def window(self) -> QWidget | None:
        return self._window

    def toggle(self) -> None:
        if self._window is None:
            self._window = self._window_factory()
        if self._window.isVisible():
            self._window.hide()
        else:
            self._window.show()
            self._window.raise_()

    def close(self) -> None:
        if self._window is not None:
            self._window.close()
