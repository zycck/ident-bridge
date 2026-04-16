# -*- coding: utf-8 -*-
"""Window-chrome helpers for MainWindow/title-bar coordination."""

from PySide6.QtCore import QEvent


class MainWindowChromeController:
    def __init__(self, *, window, title_bar) -> None:
        self._window = window
        self._title_bar = title_bar

    def wire(self) -> None:
        self._title_bar.minimize_clicked.connect(self._window.showMinimized)
        self._title_bar.maximize_clicked.connect(self.toggle_maximize)
        self._title_bar.close_clicked.connect(self._window.close)

    def toggle_maximize(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()
        self._title_bar.update_max_icon(self._window.isMaximized())

    def handle_change_event(self, event) -> None:
        if event.type() == QEvent.Type.WindowStateChange:
            self._title_bar.update_max_icon(self._window.isMaximized())

