"""Tests for extracted MainWindow chrome controller."""

from PySide6.QtCore import QObject, QEvent, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from app.ui.main_window_chrome import (
    MainWindowChromeController,
    WindowResizeController,
    build_resize_handle_layouts,
)


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


def test_build_resize_handle_layouts_covers_all_window_edges() -> None:
    layouts = build_resize_handle_layouts(QRect(0, 0, 900, 600), border=6)

    assert len(layouts) == 8
    assert layouts[0][1] == QRect(0, 0, 6, 6)
    assert layouts[1][1] == QRect(6, 0, 888, 6)
    assert layouts[3][1] == QRect(0, 6, 6, 588)
    assert layouts[-1][1] == QRect(894, 594, 6, 6)


class _FakeWindowHandle:
    def __init__(self) -> None:
        self.calls: list[Qt.Edge | Qt.Edges] = []

    def startSystemResize(self, edges: Qt.Edge | Qt.Edges) -> bool:  # noqa: N802
        self.calls.append(edges)
        return True


class _ResizeWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.fake_window_handle = _FakeWindowHandle()

    def windowHandle(self):  # type: ignore[override]
        return self.fake_window_handle


def test_resize_controller_creates_handles_and_starts_system_resize(qtbot) -> None:
    window = _ResizeWindow()
    window.resize(500, 320)
    qtbot.addWidget(window)
    controller = WindowResizeController(window=window)

    controller.wire()
    window.show()
    qtbot.wait(10)

    handles = controller.handles()
    assert len(handles) == 8
    right_handle = next(handle for handle in handles if handle.edges == Qt.Edge.RightEdge)

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPoint(1, max(1, right_handle.height() // 2)),
        QPoint(1, max(1, right_handle.height() // 2)),
        QPoint(1, max(1, right_handle.height() // 2)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    right_handle.mousePressEvent(event)

    assert window.fake_window_handle.calls == [Qt.Edge.RightEdge]
