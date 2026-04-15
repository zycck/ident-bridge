"""DebugWindow — floating log panel for development."""
from __future__ import annotations

import re

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
    "  background: #0B0D12;"
    "  color: #D4D4D8;"
    "  border: 1px solid #1E1E24;"
    "  border-radius: 6px;"
    "  font-family: Cascadia Code, Consolas, 'Courier New', monospace;"
    "  font-size: 9pt;"
    "}"
)

# Per-level colors for the dark debug viewer.
_LEVEL_COLORS: dict[str, str] = {
    "DEBUG":    "#71717A",   # zinc-500 — muted
    "INFO":     "#22D3EE",   # cyan-400
    "WARNING":  "#FBBF24",   # amber-400
    "ERROR":    "#F87171",   # red-400
    "CRITICAL": "#EF4444",   # red-500 + bold
}

# Parses lines produced by the formatter:
#   "HH:MM:SS [LEVEL] logger.name: message"
_LINE_RE = re.compile(r"^(\d{2}:\d{2}:\d{2}) \[(\w+)\] ([^:]+): (.*)$")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_line(text: str) -> str:
    """Colorize a log line into HTML for the dark debug viewer."""
    m = _LINE_RE.match(text)
    if not m:
        # Unknown format — render as-is in default text color.
        return f'<span style="color:#D4D4D8">{_esc(text)}</span>'

    ts, level, logger, msg = m.groups()
    level_color = _LEVEL_COLORS.get(level, "#A1A1AA")
    weight = "700" if level == "CRITICAL" else "600"

    return (
        f'<span style="color:#52525B">{_esc(ts)}</span> '
        f'<span style="color:{level_color}; font-weight:{weight}">'
        f'[{_esc(level)}]</span> '
        f'<span style="color:#A78BFA">{_esc(logger)}</span>'
        f'<span style="color:#52525B">:</span> '
        f'<span style="color:#D4D4D8">{_esc(msg)}</span>'
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
        self._log.appendHtml(_format_line(text))
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._log.toPlainText())
