# -*- coding: utf-8 -*-
"""Tests for extracted title-bar interaction controller."""

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt

from app.ui.title_bar_controller import TitleBarInteractionController


class _FakeButton:
    def __init__(self) -> None:
        self._icon_default = "default"
        self._icon_hover = "hover"
        self.icons: list[str] = []

    def setIcon(self, icon) -> None:
        self.icons.append(icon)


class _FakeRect:
    def __init__(self, top_left: QPoint) -> None:
        self._top_left = top_left

    def topLeft(self) -> QPoint:
        return self._top_left


class _FakeWindow:
    def __init__(self, *, maximized: bool = False) -> None:
        self._maximized = maximized
        self.moves: list[QPoint] = []

    def frameGeometry(self) -> _FakeRect:
        return _FakeRect(QPoint(10, 10))

    def isMaximized(self) -> bool:
        return self._maximized

    def move(self, point: QPoint) -> None:
        self.moves.append(point)


class _FakeMouseEvent:
    def __init__(
        self,
        *,
        button: Qt.MouseButton,
        buttons: Qt.MouseButton,
        global_point: QPoint,
    ) -> None:
        self._button = button
        self._buttons = buttons
        self._global_point = global_point
        self.accepted = 0

    def button(self) -> Qt.MouseButton:
        return self._button

    def buttons(self) -> Qt.MouseButton:
        return self._buttons

    def globalPosition(self) -> QPointF:
        return QPointF(self._global_point)

    def accept(self) -> None:
        self.accepted += 1


def test_title_bar_controller_swaps_hover_icons() -> None:
    controller = TitleBarInteractionController(
        window_provider=lambda: None,
        emit_maximize=lambda: None,
    )
    button = _FakeButton()

    controller.handle_event_filter(button, QEvent(QEvent.Type.Enter))
    controller.handle_event_filter(button, QEvent(QEvent.Type.Leave))

    assert button.icons == ["hover", "default"]


def test_title_bar_controller_handles_drag_move() -> None:
    window = _FakeWindow()
    controller = TitleBarInteractionController(
        window_provider=lambda: window,
        emit_maximize=lambda: None,
    )
    press = _FakeMouseEvent(
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.LeftButton,
        global_point=QPoint(30, 30),
    )
    move = _FakeMouseEvent(
        button=Qt.MouseButton.NoButton,
        buttons=Qt.MouseButton.LeftButton,
        global_point=QPoint(50, 60),
    )

    assert controller.handle_mouse_press(press) is True
    assert controller.handle_mouse_move(move) is True

    assert press.accepted == 1
    assert move.accepted == 1
    assert window.moves == [QPoint(30, 40)]


def test_title_bar_controller_skips_window_move_when_maximized() -> None:
    window = _FakeWindow(maximized=True)
    controller = TitleBarInteractionController(
        window_provider=lambda: window,
        emit_maximize=lambda: None,
    )
    controller.handle_mouse_press(
        _FakeMouseEvent(
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
            global_point=QPoint(30, 30),
        )
    )
    controller.handle_mouse_move(
        _FakeMouseEvent(
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
            global_point=QPoint(50, 60),
        )
    )

    assert window.moves == []


def test_title_bar_controller_emits_maximize_on_double_click() -> None:
    maximize_calls: list[bool] = []
    controller = TitleBarInteractionController(
        window_provider=lambda: None,
        emit_maximize=lambda: maximize_calls.append(True),
    )
    event = _FakeMouseEvent(
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.LeftButton,
        global_point=QPoint(0, 0),
    )

    assert controller.handle_mouse_double_click(event) is True
    assert maximize_calls == [True]
    assert event.accepted == 1
