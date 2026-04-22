"""Dialog for connecting a Google Apps Script webhook."""

from __future__ import annotations

from pathlib import Path
from typing import override

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Theme


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

_TITLE = "\u041f\u043e\u0434\u043a\u043b\u044e\u0447\u0435\u043d\u0438\u0435 Google \u0422\u0430\u0431\u043b\u0438\u0446"
_INTRO = (
    "1. \u0412\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0430\u0434\u0440\u0435\u0441 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438.\n"
    "2. \u0421\u043a\u043e\u043f\u0438\u0440\u0443\u0439\u0442\u0435 \u043a\u043e\u0434 \u043d\u0438\u0436\u0435 \u0432 Apps Script.\n"
    "3. \u041e\u043f\u0443\u0431\u043b\u0438\u043a\u0443\u0439\u0442\u0435 \u043f\u0440\u043e\u0435\u043a\u0442 \u043a\u0430\u043a \u0432\u0435\u0431-\u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435."
)
_WEBHOOK_LABEL = "\u0410\u0434\u0440\u0435\u0441 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0438"
_CODE_LABEL = "\u041a\u043e\u0434 \u0434\u043b\u044f Apps Script"
_PREVIEW_PLACEHOLDER = "\u041a\u043e\u0434 \u0431\u0443\u0434\u0435\u0442 \u043f\u043e\u043a\u0430\u0437\u0430\u043d \u0437\u0434\u0435\u0441\u044c."
_SAVE_LABEL = "\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c"
_CANCEL_LABEL = "\u041e\u0442\u043c\u0435\u043d\u0430"
_SHIM_FALLBACK = "// \u043a\u043e\u0434 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d"


def _shim_preview_text() -> str:
    resolved = Path(__file__).resolve()
    shim_path = None
    for parent in resolved.parents:
        candidate = parent / "resources" / "gas-shim" / "shim.gs"
        if candidate.exists():
            shim_path = candidate
            break
    if shim_path is None:
        return _SHIM_FALLBACK
    try:
        return shim_path.read_text(encoding="utf-8")
    except OSError:
        return _SHIM_FALLBACK


class GasSetupWizard(QDialog):
    """Collects webhook settings for connecting a sheet."""

    def __init__(
        self,
        *,
        initial_webhook_url: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_TITLE)
        self.resize(760, 620)
        self.setStyleSheet(_DIALOG_QSS)
        self._build_ui()
        self._webhook_url_edit.setText((initial_webhook_url or "").strip())
        self._refresh_actions()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        self._intro_label = QLabel(_INTRO, self)
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
        form.addRow(_WEBHOOK_LABEL, self._webhook_url_edit)

        self._code_label = QLabel(_CODE_LABEL, self)
        root.addWidget(self._code_label)

        self._shim_preview = QPlainTextEdit(self)
        self._shim_preview.setReadOnly(True)
        self._shim_preview.setPlaceholderText(_PREVIEW_PLACEHOLDER)
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
        self._apply_btn.setText(_SAVE_LABEL)
        self._cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_btn.setText(_CANCEL_LABEL)
        root.addWidget(self._buttons)

    def _refresh_actions(self) -> None:
        webhook_url = self._webhook_url_edit.text().strip()
        self._apply_btn.setEnabled(bool(webhook_url))

    def selected_config(self) -> dict[str, str]:
        return {
            "webhook_url": self._webhook_url_edit.text().strip(),
        }

    @override
    def accept(self) -> None:
        self._webhook_url_edit.setText(self._webhook_url_edit.text().strip())
        super().accept()
