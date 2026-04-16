# -*- coding: utf-8 -*-
"""Dashboard update-banner widget extracted from DashboardWidget."""

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton


class DashboardUpdateBanner(QFrame):
    update_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._update_url = ""
        self.setObjectName("updateBanner")
        self.setVisible(False)

        banner_layout = QHBoxLayout(self)
        banner_layout.setContentsMargins(12, 8, 12, 8)

        self._update_label = QLabel("Доступна версия — ")
        self._update_btn = QPushButton("Обновить")
        self._update_btn.setFlat(True)
        self._update_btn.clicked.connect(self._on_update_clicked)

        banner_layout.addWidget(self._update_label)
        banner_layout.addWidget(self._update_btn)
        banner_layout.addStretch()

    @property
    def update_url(self) -> str:
        return self._update_url

    def label_text(self) -> str:
        return self._update_label.text()

    def button(self) -> QPushButton:
        return self._update_btn

    def show_update(self, version: str, url: str) -> None:
        self._update_url = url
        self._update_label.setText(f"Доступна версия {version}  ·  ")
        self.setVisible(True)

    def set_in_progress(self, running: bool) -> None:
        self._update_btn.setEnabled(not running)
        self._update_btn.setText("Загрузка…" if running else "Обновить")

    @Slot()
    def _on_update_clicked(self) -> None:
        self.update_requested.emit(self._update_url)
