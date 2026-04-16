"""DebugWindow — floating log panel for development."""

from PySide6.QtCore import Qt, Slot

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import DEBUG_LOG_BLOCK_LIMIT

from app.ui.debug_window_log_controller import DebugWindowLogController
from app.ui.debug_window_formatting import format_log_line_html

_STYLE_LOG = (
    "QPlainTextEdit {"
    "  background: #0B0D12;"
    "  color: #D4D4D8;"
    "  border: 1px solid #1E1E24;"
    "  border-radius: 6px;"
    "  font-family: Cascadia Code, Consolas, 'Courier New', monospace;"
    "  font-size: 9pt;"
    "}"
)


class DebugWindow(QDialog):
    """Floating window that mirrors all Python logging output in real-time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Debug — iDentBridge")
        self.resize(1000, 560)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self._build_ui()
        self._log_controller = DebugWindowLogController(
            on_message=self._append_message,
            parent=self,
        )
        self._log_controller.connect()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 10)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(DEBUG_LOG_BLOCK_LIMIT)
        self._log.setStyleSheet(_STYLE_LOG)
        font = QFont("Cascadia Code", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(font)

        hdr = QHBoxLayout()
        lbl = QLabel("Debug log")
        lbl.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        clear_btn = QPushButton("Очистить")
        clear_btn.setFixedWidth(90)
        clear_btn.clicked.connect(self._log.clear)

        copy_btn = QPushButton("Копировать")
        copy_btn.setFixedWidth(100)
        copy_btn.clicked.connect(self._copy_all)

        hdr.addWidget(clear_btn)
        hdr.addWidget(copy_btn)

        root.addLayout(hdr)
        root.addWidget(self._log, stretch=1)

    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._log_controller.connect()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._log_controller.disconnect()
        event.accept()

    # ------------------------------------------------------------------
    @Slot(str)
    def _append_message(self, text: str) -> None:
        self._log.appendHtml(format_log_line_html(text))
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._log.toPlainText())
