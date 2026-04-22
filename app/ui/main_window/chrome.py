"""Window-chrome helpers for MainWindow/title-bar coordination."""

from collections.abc import Iterable

from PySide6.QtCore import QEvent, QObject, QRect, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

_RESIZE_BORDER_PX = 6


def build_resize_handle_layouts(
    rect: QRect,
    border: int = _RESIZE_BORDER_PX,
) -> list[tuple[Qt.Edge | Qt.Edges, QRect, Qt.CursorShape]]:
    width = max(0, rect.width())
    height = max(0, rect.height())
    inner_width = max(0, width - border * 2)
    inner_height = max(0, height - border * 2)
    return [
        (
            Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
            QRect(0, 0, border, border),
            Qt.CursorShape.SizeFDiagCursor,
        ),
        (
            Qt.Edge.TopEdge,
            QRect(border, 0, inner_width, border),
            Qt.CursorShape.SizeVerCursor,
        ),
        (
            Qt.Edge.TopEdge | Qt.Edge.RightEdge,
            QRect(width - border, 0, border, border),
            Qt.CursorShape.SizeBDiagCursor,
        ),
        (
            Qt.Edge.LeftEdge,
            QRect(0, border, border, inner_height),
            Qt.CursorShape.SizeHorCursor,
        ),
        (
            Qt.Edge.RightEdge,
            QRect(width - border, border, border, inner_height),
            Qt.CursorShape.SizeHorCursor,
        ),
        (
            Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
            QRect(0, height - border, border, border),
            Qt.CursorShape.SizeBDiagCursor,
        ),
        (
            Qt.Edge.BottomEdge,
            QRect(border, height - border, inner_width, border),
            Qt.CursorShape.SizeVerCursor,
        ),
        (
            Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
            QRect(width - border, height - border, border, border),
            Qt.CursorShape.SizeFDiagCursor,
        ),
    ]


class _ResizeHandle(QWidget):
    def __init__(
        self,
        *,
        parent: QWidget,
        edges: Qt.Edge | Qt.Edges,
        cursor: Qt.CursorShape,
        start_resize,
    ) -> None:
        super().__init__(parent)
        self._edges = edges
        self._start_resize = start_resize
        self.setObjectName("windowResizeHandle")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setCursor(cursor)

    @property
    def edges(self) -> Qt.Edge | Qt.Edges:
        return self._edges

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._start_resize(
            self._edges
        ):
            event.accept()
            return
        super().mousePressEvent(event)


class WindowResizeController(QObject):
    def __init__(self, *, window: QWidget, border: int = _RESIZE_BORDER_PX) -> None:
        super().__init__(window)
        self._window = window
        self._border = border
        self._handles: list[_ResizeHandle] = []

    def wire(self) -> None:
        if self._handles:
            return
        for edges, geometry, cursor in build_resize_handle_layouts(
            self._window.rect(),
            self._border,
        ):
            handle = _ResizeHandle(
                parent=self._window,
                edges=edges,
                cursor=cursor,
                start_resize=self._start_resize,
            )
            handle.setGeometry(geometry)
            handle.raise_()
            self._handles.append(handle)
        self._window.installEventFilter(self)
        self.refresh()

    def handles(self) -> list[QWidget]:
        return list(self._handles)

    def refresh(self) -> None:
        visible = self._can_resize()
        for handle, (_edges, geometry, _cursor) in zip(
            self._handles,
            build_resize_handle_layouts(self._window.rect(), self._border),
            strict=False,
        ):
            handle.setGeometry(geometry)
            handle.raise_()
            handle.setVisible(visible and geometry.width() > 0 and geometry.height() > 0)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._window and event.type() in {
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.WindowStateChange,
        }:
            self.refresh()
        return super().eventFilter(watched, event)

    def _can_resize(self) -> bool:
        return not self._window.isMaximized() and not self._window.isFullScreen()

    def _start_resize(self, edges: Qt.Edge | Qt.Edges) -> bool:
        if not self._can_resize():
            return False
        handle = self._window.windowHandle()
        if handle is None:
            return False
        return bool(handle.startSystemResize(edges))


class MainWindowChromeController:
    def __init__(self, *, window, title_bar) -> None:
        self._window = window
        self._title_bar = title_bar
        self._resize = (
            WindowResizeController(window=window) if isinstance(window, QWidget) else None
        )

    def wire(self) -> None:
        self._title_bar.minimize_clicked.connect(self._window.showMinimized)
        self._title_bar.maximize_clicked.connect(self.toggle_maximize)
        self._title_bar.close_clicked.connect(self._window.close)
        if self._resize is not None:
            self._resize.wire()

    def toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self._title_bar.update_max_icon(self._window.isMaximized())
        if self._resize is not None:
            self._resize.refresh()

    def handle_change_event(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            self._title_bar.update_max_icon(self._window.isMaximized())
            if self._resize is not None:
                self._resize.refresh()

