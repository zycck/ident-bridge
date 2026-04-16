# -*- coding: utf-8 -*-
"""Interaction controller extracted from CustomTitleBar."""

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent


class TitleBarInteractionController:
    """Owns hover and drag behavior for the custom title bar."""

    def __init__(
        self,
        *,
        window_provider: Callable[[], object | None],
        emit_maximize: Callable[[], None],
    ) -> None:
        self._window_provider = window_provider
        self._emit_maximize = emit_maximize
        self._drag_pos: QPoint | None = None

    def handle_event_filter(self, obj, event: QEvent) -> bool:
        if hasattr(obj, "_icon_hover"):
            if event.type() == QEvent.Type.Enter:
                obj.setIcon(obj._icon_hover)
            elif event.type() == QEvent.Type.Leave:
                obj.setIcon(obj._icon_default)
        return False

    def handle_mouse_press(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        window = self._window_provider()
        if window is not None:
            self._drag_pos = (
                event.globalPosition().toPoint() - window.frameGeometry().topLeft()
            )
        event.accept()
        return True

    def handle_mouse_move(self, event: QMouseEvent) -> bool:
        if self._drag_pos is None:
            return False
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return False
        window = self._window_provider()
        if window is not None and not window.isMaximized():
            window.move(event.globalPosition().toPoint() - self._drag_pos)
        event.accept()
        return True

    def handle_mouse_release(self, event: QMouseEvent) -> bool:
        self._drag_pos = None
        return False

    def handle_mouse_double_click(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._emit_maximize()
        event.accept()
        return True
