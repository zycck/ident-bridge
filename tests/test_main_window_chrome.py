# -*- coding: utf-8 -*-
"""Tests for extracted MainWindow chrome controller."""

from PySide6.QtCore import QObject, QEvent, Signal

from app.ui.main_window_chrome import MainWindowChromeController


class _FakeTitleBar(QObject):
    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.updated: list[bool] = []

    def update_max_icon(self, is_maximized: bool) -> None:
        self.updated.append(is_maximized)


class _FakeWindow:
    def __init__(self) -> None:
        self.maximized = False
        self.minimized_calls = 0
        self.closed_calls = 0
        self.show_normal_calls = 0
        self.show_maximized_calls = 0

    def showMinimized(self) -> None:
        self.minimized_calls += 1

    def close(self) -> None:
        self.closed_calls += 1

    def isMaximized(self) -> bool:
        return self.maximized

    def showNormal(self) -> None:
        self.maximized = False
        self.show_normal_calls += 1

    def showMaximized(self) -> None:
        self.maximized = True
        self.show_maximized_calls += 1


def test_chrome_controller_wires_titlebar_minimize_and_close() -> None:
    title_bar = _FakeTitleBar()
    window = _FakeWindow()
    controller = MainWindowChromeController(window=window, title_bar=title_bar)

    controller.wire()
    title_bar.minimize_clicked.emit()
    title_bar.close_clicked.emit()

    assert window.minimized_calls == 1
    assert window.closed_calls == 1


def test_chrome_controller_toggle_maximize_roundtrips_state_and_icon() -> None:
    title_bar = _FakeTitleBar()
    window = _FakeWindow()
    controller = MainWindowChromeController(window=window, title_bar=title_bar)

    controller.toggle_maximize()
    controller.toggle_maximize()

    assert window.show_maximized_calls == 1
    assert window.show_normal_calls == 1
    assert title_bar.updated == [True, False]


def test_chrome_controller_wires_maximize_signal() -> None:
    title_bar = _FakeTitleBar()
    window = _FakeWindow()
    controller = MainWindowChromeController(window=window, title_bar=title_bar)

    controller.wire()
    title_bar.maximize_clicked.emit()

    assert window.show_maximized_calls == 1
    assert title_bar.updated == [True]


def test_chrome_controller_handles_only_window_state_change_events() -> None:
    title_bar = _FakeTitleBar()
    window = _FakeWindow()
    controller = MainWindowChromeController(window=window, title_bar=title_bar)

    controller.handle_change_event(QEvent(QEvent.Type.Show))
    assert title_bar.updated == []

    window.maximized = True
    controller.handle_change_event(QEvent(QEvent.Type.WindowStateChange))
    assert title_bar.updated == [True]
