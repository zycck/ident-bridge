"""DebugWindow — floating log panel for development."""

from typing import override

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QCloseEvent, QFont, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import DEBUG_LOG_BLOCK_LIMIT
from app.core.resource_monitor import ResourceMonitor

from app.ui.debug_window_log_controller import DebugWindowLogController
from app.ui.debug_window_formatting import (
    filter_log_lines,
    format_log_line_html,
    get_log_level,
)
from app.ui.resource_monitor_bar import ResourceMonitorBar

_STYLE_LOG = (
    "QTextEdit {"
    "  background: #0B0D12;"
    "  color: #D4D4D8;"
    "  border: 1px solid #1E1E24;"
    "  border-radius: 6px;"
    "  font-family: Cascadia Code, Consolas, 'Courier New', monospace;"
    "  font-size: 9pt;"
    "}"
)

_LOG_LEVEL_OPTIONS: list[tuple[str, str | None]] = [
    ("Все", None),
    ("DEBUG", "DEBUG"),
    ("INFO", "INFO"),
    ("WARNING", "WARNING"),
    ("ERROR", "ERROR"),
    ("CRITICAL", "CRITICAL"),
]


class DebugWindow(QDialog):
    """Floating window that mirrors all Python logging output in real-time."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Debug — iDentBridge")
        self.resize(1000, 560)
        self.setWindowFlag(Qt.WindowType.Window, True)
        # Monitor is constructed eagerly (cheap) but only starts ticking
        # while the window is visible — see showEvent / closeEvent.
        self._resource_monitor = ResourceMonitor(interval_ms=1000, parent=self)
        self._log_entries: list[str] = []
        self._log_level_filter: str | None = None
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

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self._log.document().setMaximumBlockCount(DEBUG_LOG_BLOCK_LIMIT)
        self._log.setStyleSheet(_STYLE_LOG)
        font = QFont("Cascadia Code", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(font)

        hdr = QHBoxLayout()
        lbl = QLabel("Debug log")
        lbl.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        filter_lbl = QLabel("Уровень")
        filter_lbl.setStyleSheet("color: #6B7280; font-size: 9pt; font-weight: 600;")
        hdr.addWidget(filter_lbl)

        self._level_filter = QComboBox()
        self._level_filter.addItems([label for label, _ in _LOG_LEVEL_OPTIONS])
        for idx, (_, level) in enumerate(_LOG_LEVEL_OPTIONS):
            self._level_filter.setItemData(idx, level)
        self._level_filter.currentIndexChanged.connect(self._on_level_filter_changed)
        hdr.addWidget(self._level_filter)

        clear_btn = QPushButton("Очистить")
        clear_btn.setFixedWidth(90)
        clear_btn.clicked.connect(self._clear_log)

        copy_btn = QPushButton("Копировать")
        copy_btn.setFixedWidth(100)
        copy_btn.clicked.connect(self._copy_all)

        hdr.addWidget(clear_btn)
        hdr.addWidget(copy_btn)

        root.addLayout(hdr)
        root.addWidget(self._log, stretch=1)

        self._resource_bar = ResourceMonitorBar(self._resource_monitor, self)
        root.addWidget(self._resource_bar)

    # ------------------------------------------------------------------
    @override
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._log_controller.connect()
        self._resource_monitor.start()

    @override
    def closeEvent(self, event: QCloseEvent) -> None:
        self._log_controller.disconnect()
        self._resource_monitor.stop()
        event.accept()

    # ------------------------------------------------------------------
    @Slot(str)
    def _append_message(self, text: str) -> None:
        self._log_entries.append(text)
        if len(self._log_entries) > DEBUG_LOG_BLOCK_LIMIT:
            overflow = len(self._log_entries) - DEBUG_LOG_BLOCK_LIMIT
            del self._log_entries[:overflow]
        if not self._message_matches_filter(text):
            return
        self._append_html_line(text)

    @Slot(int)
    def _on_level_filter_changed(self, index: int) -> None:
        self._log_level_filter = self._level_filter.itemData(index)
        self._render_log()

    def _message_matches_filter(self, text: str) -> bool:
        if self._log_level_filter is None:
            return True
        return get_log_level(text) == self._log_level_filter

    def _append_html_line(self, text: str) -> None:
        self._log.append(format_log_line_html(text))
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _render_log(self) -> None:
        self._log.clear()
        for text in filter_log_lines(self._log_entries, self._log_level_filter):
            self._append_html_line(text)

    def _clear_log(self) -> None:
        self._log_entries.clear()
        self._log.clear()

    def _copy_all(self) -> None:
        QApplication.clipboard().setText(self._log.toPlainText())
