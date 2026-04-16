# -*- coding: utf-8 -*-
"""Composite shell/layout for MainWindow."""

from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget, QPushButton
from PySide6.QtGui import QIcon

from app.ui.main_window_navigation import build_navigation_sidebar
from app.ui.title_bar import CustomTitleBar


class MainWindowShell(QWidget):
    """Owns MainWindow layout composition while reusing extracted helpers."""

    def __init__(
        self,
        *,
        current_version: str,
        stack: QStackedWidget,
        on_navigate: Callable[[int], None],
        on_debug: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._stack = stack
        self._on_navigate = on_navigate
        self._on_debug = on_debug
        self._nav_btns: list[QPushButton] = []
        self._nav_icons_normal: list[QIcon] = []
        self._nav_icons_active: list[QIcon] = []
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._title_bar = CustomTitleBar("iDentBridge", self)
        outer.addWidget(self._title_bar)

        body = QWidget(self)
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        (
            sidebar,
            self._nav_btns,
            self._nav_icons_normal,
            self._nav_icons_active,
        ) = build_navigation_sidebar(
            body,
            current_version=self._current_version,
            on_navigate=self._on_navigate,
            on_debug=self._on_debug,
        )

        root.addWidget(sidebar)
        root.addWidget(self._stack, stretch=1)

        outer.addWidget(body, stretch=1)

    def title_bar(self) -> CustomTitleBar:
        return self._title_bar

    def stack(self) -> QStackedWidget:
        return self._stack

    def nav_buttons(self) -> list[QPushButton]:
        return list(self._nav_btns)

    def normal_icons(self) -> list[QIcon]:
        return list(self._nav_icons_normal)

    def active_icons(self) -> list[QIcon]:
        return list(self._nav_icons_active)
