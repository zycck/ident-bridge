# -*- coding: utf-8 -*-
"""Application settings section extracted from SettingsWidget."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui.lucide_icons import lucide
from app.ui.theme import Theme
from app.ui.widgets import section


class SettingsAppPanel(QWidget):
    startup_toggled = Signal(bool)
    check_update_requested = Signal()

    def __init__(self, current_version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        box, app_lay = section("Приложение")

        self._startup_check = QCheckBox("Запускать с Windows")
        self._startup_check.toggled.connect(self.startup_toggled)
        app_lay.addWidget(self._startup_check)

        self._auto_update_check = QCheckBox("Проверять обновления при запуске")
        app_lay.addWidget(self._auto_update_check)

        self._version_lbl = QLabel(f"Версия: {self._current_version}")
        self._version_lbl.setStyleSheet("color: #3F3F46; font-size: 9pt;")
        app_lay.addWidget(self._version_lbl)

        self._check_update_btn = QPushButton("  Проверить обновление")
        self._check_update_btn.setIcon(
            lucide("download-cloud", color=Theme.gray_700, size=14)
        )
        self._check_update_btn.clicked.connect(self.check_update_requested)
        app_lay.addWidget(self._check_update_btn)

        root.addWidget(box)

    def startup_check(self) -> QCheckBox:
        return self._startup_check

    def auto_update_check(self) -> QCheckBox:
        return self._auto_update_check

    def check_update_button(self) -> QPushButton:
        return self._check_update_btn

    def version_text(self) -> str:
        return self._version_lbl.text()
