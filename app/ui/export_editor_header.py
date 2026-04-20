"""Header widget for ExportJobEditor."""

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.lucide_icons import lucide
from app.ui.theme import Theme

_STATUS_COLORS: dict[str, str] = {
    "idle": Theme.gray_500,
    "ok": Theme.success,
    "error": Theme.error,
    "running": Theme.info,
}


class ExportEditorHeader(QWidget):
    """Owns the editor title, status summary, and action buttons."""

    changed = Signal()
    run_requested = Signal()
    test_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.setContentsMargins(0, 0, 0, 0)

        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("cardTitle")
        self._name_edit.setPlaceholderText("Без названия")
        self._name_edit.setStyleSheet(
            f"QLineEdit#cardTitle {{"
            f"  background: transparent;"
            f"  border: 1px solid transparent;"
            f"  padding: 2px 4px;"
            f"  font-size: {Theme.font_size_md}pt;"
            f"  font-weight: {Theme.font_weight_semi};"
            f"  color: {Theme.gray_900};"
            f"  min-height: 22px;"
            f"}}"
            f"QLineEdit#cardTitle:hover {{"
            f"  background: {Theme.gray_50};"
            f"  border-radius: 4px;"
            f"}}"
            f"QLineEdit#cardTitle:focus {{"
            f"  background: {Theme.surface};"
            f"  border: 1px solid {Theme.border_strong};"
            f"  border-radius: 4px;"
            f"}}"
        )
        self._name_edit.editingFinished.connect(self.changed)
        title_col.addWidget(self._name_edit)

        self._status_summary = QLabel("Ещё не запускалось")
        self._status_summary.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"background: transparent; "
            f"padding-left: 4px;"
        )
        title_col.addWidget(self._status_summary)

        root.addLayout(title_col, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self._test_btn = QPushButton("  Тест")
        self._test_btn.setIcon(lucide("terminal", color=Theme.gray_700, size=12))
        self._test_btn.setFixedHeight(28)
        self._test_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._test_btn.setToolTip("Выполнить SQL запрос в тестовом окне")
        self._test_btn.clicked.connect(self.test_requested)
        btn_row.addWidget(self._test_btn)

        self._run_btn = QPushButton("  Запустить")
        self._run_btn.setIcon(lucide("play", color=Theme.gray_900, size=12))
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setFixedHeight(28)
        self._run_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._run_btn.setToolTip("Запустить выгрузку вручную")
        self._run_btn.clicked.connect(self.run_requested)
        btn_row.addWidget(self._run_btn)

        root.addLayout(btn_row)

    def job_name(self) -> str:
        return self._name_edit.text().strip()

    def set_job_name(self, name: str) -> None:
        with QSignalBlocker(self._name_edit):
            self._name_edit.setText(name)

    def set_run_enabled(self, enabled: bool) -> None:
        self._run_btn.setEnabled(enabled)

    def set_status(self, kind: str, text: str) -> None:
        color = _STATUS_COLORS.get(kind, Theme.gray_500)
        self._status_summary.setStyleSheet(
            f"color: {color}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"background: transparent; "
            f"padding-left: 4px;"
        )
        self._status_summary.setText(text)
