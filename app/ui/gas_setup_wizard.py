"""Окно подключения Google Apps Script."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import override

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Theme


LIBRARY_SCHEME_ID = "library_v1"

_DIALOG_QSS = (
    f"QDialog {{"
    f"  background-color: {Theme.surface_tinted};"
    f"  color: {Theme.gray_900};"
    f"}}"
    f"QLabel {{"
    f"  background: transparent;"
    f"  color: {Theme.gray_700};"
    f"}}"
    f"QLineEdit, QPlainTextEdit {{"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_900};"
    f"  border: 1px solid {Theme.border_strong};"
    f"  border-radius: {Theme.radius}px;"
    f"  padding: 8px 10px;"
    f"  selection-background-color: {Theme.primary_200};"
    f"  selection-color: {Theme.primary_900};"
    f"}}"
    f"QLineEdit:focus, QPlainTextEdit:focus {{"
    f"  border-color: {Theme.border_focus};"
    f"}}"
    f"QPlainTextEdit {{"
    f"  font-family: {Theme.font_mono};"
    f"}}"
    f"QPushButton {{"
    f"  min-height: 28px;"
    f"  padding: 0 14px;"
    f"  border: 1px solid {Theme.border_strong};"
    f"  border-radius: {Theme.radius}px;"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_700};"
    f"}}"
    f"QPushButton:hover {{"
    f"  background-color: {Theme.gray_50};"
    f"  border-color: {Theme.border_focus};"
    f"  color: {Theme.primary_800};"
    f"}}"
    f"QPushButton:disabled {{"
    f"  background-color: {Theme.gray_100};"
    f"  color: {Theme.gray_400};"
    f"}}"
    f"QPushButton#primaryBtn {{"
    f"  background-color: {Theme.primary_500};"
    f"  color: {Theme.gray_900};"
    f"  border: 1px solid {Theme.primary_600};"
    f"  font-weight: {Theme.font_weight_semi};"
    f"}}"
    f"QPushButton#primaryBtn:hover {{"
    f"  background-color: {Theme.primary_600};"
    f"  border-color: {Theme.primary_700};"
    f"}}"
)


def _shim_preview_text() -> str:
    root = Path(__file__).resolve().parents[2]
    shim_path = root / "resources" / "gas-shim" / "shim.gs"
    try:
        return shim_path.read_text(encoding="utf-8")
    except OSError:
        return "// код недоступен"


class GasSetupWizard(QDialog):
    """Собирает данные для подключения таблицы."""

    def __init__(
        self,
        *,
        initial_webhook_url: str = "",
        initial_auth_token: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Подключение Google Таблиц")
        self.resize(760, 620)
        self.setStyleSheet(_DIALOG_QSS)
        self._build_ui()
        self._webhook_url_edit.setText((initial_webhook_url or "").strip())
        if initial_auth_token:
            self._set_auth_token(initial_auth_token)
        else:
            self._generate_token()
        self._refresh_actions()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        self._intro_label = QLabel(
            "1. Вставьте адрес обработки.\n"
            "2. Если нужно, создайте ключ доступа.\n"
            "3. Скопируйте код ниже в проект Apps Script.\n"
            "4. Сохраните адрес и ключ доступа в iDentBridge.",
            self,
        )
        self._intro_label.setWordWrap(True)
        root.addWidget(self._intro_label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        root.addLayout(form)

        self._webhook_url_edit = QLineEdit(self)
        self._webhook_url_edit.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        self._webhook_url_edit.textChanged.connect(self._refresh_actions)
        form.addRow("Адрес обработки", self._webhook_url_edit)

        token_row = QHBoxLayout()
        token_row.setSpacing(8)

        self._auth_token_edit = QLineEdit(self)
        self._auth_token_edit.setPlaceholderText("Ключ доступа")
        self._auth_token_edit.textChanged.connect(self._refresh_actions)
        token_row.addWidget(self._auth_token_edit, stretch=1)

        self._generate_btn = QPushButton("Создать", self)
        self._generate_btn.clicked.connect(self._generate_token)
        token_row.addWidget(self._generate_btn)

        self._copy_btn = QPushButton("Копировать", self)
        self._copy_btn.clicked.connect(self._copy_token)
        token_row.addWidget(self._copy_btn)

        form.addRow("Ключ доступа", token_row)

        self._code_label = QLabel("Код для Apps Script", self)
        root.addWidget(self._code_label)

        self._shim_preview = QPlainTextEdit(self)
        self._shim_preview.setReadOnly(True)
        self._shim_preview.setPlaceholderText("Код будет показан здесь.")
        self._shim_preview.setPlainText(_shim_preview_text())
        root.addWidget(self._shim_preview, stretch=1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._apply_btn = self._buttons.button(QDialogButtonBox.StandardButton.Save)
        self._apply_btn.setObjectName("primaryBtn")
        self._apply_btn.setText("Сохранить")
        self._cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_btn.setText("Отмена")
        root.addWidget(self._buttons)

    def _set_auth_token(self, value: str) -> None:
        with QSignalBlocker(self._auth_token_edit):
            self._auth_token_edit.setText((value or "").strip())
        self._refresh_actions()

    def _generate_token(self) -> None:
        self._set_auth_token(secrets.token_urlsafe(32))

    def _copy_token(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._auth_token_edit.text().strip())

    def _refresh_actions(self) -> None:
        webhook_url = self._webhook_url_edit.text().strip()
        auth_token = self._auth_token_edit.text().strip()
        self._apply_btn.setEnabled(bool(webhook_url and auth_token))

    def selected_config(self) -> dict[str, str]:
        return {
            "webhook_url": self._webhook_url_edit.text().strip(),
            "auth_token": self._auth_token_edit.text().strip(),
            "scheme_id": LIBRARY_SCHEME_ID,
        }

    @override
    def accept(self) -> None:
        self._webhook_url_edit.setText(self._webhook_url_edit.text().strip())
        self._auth_token_edit.setText(self._auth_token_edit.text().strip())
        super().accept()
