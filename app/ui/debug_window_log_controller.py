# -*- coding: utf-8 -*-
"""Logging bridge extracted from DebugWindow."""

from collections.abc import Callable

from PySide6.QtCore import QObject

from app.core.app_logger import get_handler


class DebugWindowLogController(QObject):
    """Owns handler subscription and history replay for the debug window."""

    def __init__(
        self,
        *,
        on_message: Callable[[str], None],
        get_handler_fn: Callable[[], object] = get_handler,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_message = on_message
        self._get_handler = get_handler_fn
        self._connected = False
        self._history_loaded = False

    def connect(self) -> None:
        if self._connected:
            return
        handler = self._get_handler()
        if not self._history_loaded:
            for line in handler.history:
                self._on_message(line)
            self._history_loaded = True
        handler.message.connect(self._on_message)
        self._connected = True

    def disconnect(self) -> None:
        if not self._connected:
            return
        self._get_handler().message.disconnect(self._on_message)
        self._connected = False
