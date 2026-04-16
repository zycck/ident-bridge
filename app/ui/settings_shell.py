# -*- coding: utf-8 -*-
"""Composite shell for the settings screen."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.ui.lucide_icons import lucide
from app.ui.settings_app_panel import SettingsAppPanel
from app.ui.settings_sql_panel import SettingsSqlPanel
from app.ui.theme import Theme


class SettingsShell(QWidget):
    """Owns the settings screen layout and bottom action bar."""

    reset_requested = Signal()
    save_requested = Signal()

    def __init__(
        self,
        current_version: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget(self)
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        self._sql_panel = SettingsSqlPanel(self)
        layout.addWidget(self._sql_panel)

        self._app_panel = SettingsAppPanel(self._current_version, self)
        layout.addWidget(self._app_panel)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addStretch()

        self._reset_btn = QPushButton("  Сбросить", self)
        self._reset_btn.setIcon(lucide("rotate-ccw", color=Theme.gray_700, size=14))
        self._reset_btn.clicked.connect(self.reset_requested)
        btn_row.addWidget(self._reset_btn)

        self._save_btn = QPushButton("  Сохранить", self)
        self._save_btn.setObjectName("primaryBtn")
        self._save_btn.setIcon(lucide("save", color=Theme.gray_900, size=14))
        self._save_btn.clicked.connect(self.save_requested)
        btn_row.addWidget(self._save_btn)

        layout.addLayout(btn_row)
        layout.addStretch()

    def sql_panel(self) -> SettingsSqlPanel:
        return self._sql_panel

    def app_panel(self) -> SettingsAppPanel:
        return self._app_panel

    def reset_button(self) -> QPushButton:
        return self._reset_btn

    def save_button(self) -> QPushButton:
        return self._save_btn
