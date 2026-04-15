"""DebugWindow — floating log panel for development."""
from __future__ import annotations

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

from app.core.app_logger import get_handler

_STYLE_LOG = (
    "QPlainTextEdit {"
    "  background: #080A0E;"
    "  color: #A1A1AA;"
    "  border: 1px solid #1E1E24;"
    "  border-radius: 6px;"
    "  font-family: Consolas, 'Courier New', monospace;"
    "  font-size: 9pt;"
    "}"
)


class DebugWindow(QDialog):
    """Floating window that mirrors all Python logging output in real-time."""

    _MAX_BLOCKS = 3000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Debug — iDentBridge")
        self.resize(1000, 560)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self._connected = False
        self._history_loaded = False
        self._build_ui()
        self._connect_log()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 10)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(self._MAX_BLOCKS)
        self._log.setStyleSheet(_STYLE_LOG)
        font = QFont("Consolas", 9)
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
    def _connect_log(self) -> None:
        if not self._connected:
            handler = get_handler()
            if not self._history_loaded:
                # Replay buffered history before connecting live feed
                for line in handler.history:
                    self._on_message(line)
                self._history_loaded = True
            handler.message.connect(self._on_message)
            self._connected = True

    def _disconnect_log(self) -> None:
        if self._connected:
            get_handler().message.disconnect(self._on_message)
            self._connected = False

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._connect_log()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._disconnect_log()
        event.accept()

    # ------------------------------------------------------------------
    @Slot(str)
    def _on_message(self, text: str) -> None:
        if "[ERROR  ]" in text or "[CRITICAL]" in text:
            text = f'<span style="color:#F87171">{_esc(text)}</span>'
            self._log.appendHtml(text)
        elif "[WARNING]" in text:
            text = f'<span style="color:#FCD34D">{_esc(text)}</span>'
            self._log.appendHtml(text)
        elif "[DEBUG  ]" in text:
            text = f'<span style="color:#52525B">{_esc(text)}</span>'
            self._log.appendHtml(text)
        else:
            self._log.appendPlainText(text)

        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._log.toPlainText())


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
