# -*- coding: utf-8 -*-
"""Dialog shell extracted from SqlEditorDialog."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.sql_editor import SqlEditor


class SqlEditorDialogShell(QWidget):
    """Owns the dialog UI composition for the full-window SQL editor."""

    accept_requested = Signal()
    reject_requested = Signal()
    format_requested = Signal()

    def __init__(
        self,
        initial_text: str,
        *,
        has_formatter: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._has_formatter = has_formatter
        self._build_ui(initial_text)

    def _build_ui(self, initial_text: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._editor = SqlEditor()
        self._editor.setPlainText(initial_text)
        self._editor.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._editor, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._format_btn: QPushButton | None = None
        if self._has_formatter:
            self._format_btn = QPushButton("Форматировать")
            self._format_btn.setFixedHeight(32)
            self._format_btn.clicked.connect(self.format_requested)
            btn_row.addWidget(self._format_btn)

        btn_row.addStretch()

        self._cancel_btn = QPushButton("Отмена")
        self._cancel_btn.setFixedHeight(32)
        self._cancel_btn.clicked.connect(self.reject_requested)
        btn_row.addWidget(self._cancel_btn)

        self._save_btn = QPushButton("Сохранить")
        self._save_btn.setObjectName("primaryBtn")
        self._save_btn.setFixedHeight(32)
        self._save_btn.clicked.connect(self.accept_requested)
        btn_row.addWidget(self._save_btn)

        layout.addLayout(btn_row)

    def editor(self) -> SqlEditor:
        return self._editor

    def text(self) -> str:
        return self._editor.toPlainText()

    def set_text(self, text: str) -> None:
        self._editor.setPlainText(text)

    def format_button(self) -> QPushButton | None:
        return self._format_btn

    def save_button(self) -> QPushButton:
        return self._save_btn

    def cancel_button(self) -> QPushButton:
        return self._cancel_btn
