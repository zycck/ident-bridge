# -*- coding: utf-8 -*-
"""History panel widget used by ExportJobEditor."""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.config import ExportHistoryEntry
from app.core.constants import HISTORY_MAX
from app.ui.history_row import HistoryRow
from app.ui.theme import Theme
from app.ui.widgets import hsep


class ExportHistoryPanel(QWidget):
    """Owns export-job history data and its UI rendering."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[ExportHistoryEntry] = []
        self._build_ui()
        self._rebuild()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._hist_sep = hsep()
        root.addSpacing(4)
        root.addWidget(self._hist_sep)
        root.addSpacing(4)

        self._history_hdr_row = QWidget()
        self._history_hdr_row.setStyleSheet("background: transparent;")
        hdr_layout = QHBoxLayout(self._history_hdr_row)
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(8)

        self._history_hdr = QLabel("История")
        self._history_hdr.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_base}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent;"
        )
        hdr_layout.addWidget(self._history_hdr)
        hdr_layout.addStretch()

        self._history_clear_btn = QPushButton("Очистить")
        self._history_clear_btn.setFlat(True)
        self._history_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._history_clear_btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: none; background: transparent; padding: 0;"
            f"  color: {Theme.gray_500};"
            f"  text-decoration: underline;"
            f"}}"
            f"QPushButton:hover {{ color: {Theme.error}; }}"
        )
        self._history_clear_btn.clicked.connect(self._on_clear_history)
        hdr_layout.addWidget(self._history_clear_btn)

        root.addWidget(self._history_hdr_row)

        self._history_container = QWidget()
        self._history_container.setStyleSheet("background: transparent;")
        self._history_layout = QVBoxLayout(self._history_container)
        self._history_layout.setContentsMargins(0, 0, 0, 0)
        self._history_layout.setSpacing(2)

        self._history_scroll = QScrollArea()
        self._history_scroll.setWidget(self._history_container)
        self._history_scroll.setWidgetResizable(True)
        self._history_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._history_scroll.setMaximumHeight(280)
        self._history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._history_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        root.addWidget(self._history_scroll)

    def history(self) -> list[ExportHistoryEntry]:
        return list(self._history)

    def set_history(self, history: list[ExportHistoryEntry]) -> None:
        self._history = list(history)
        self._rebuild()

    def prepend_entry(self, entry: ExportHistoryEntry) -> None:
        self._history.insert(0, entry)
        if len(self._history) > HISTORY_MAX:
            self._history = self._history[:HISTORY_MAX]
        self._rebuild()
        self.changed.emit()

    def latest_entry(self) -> ExportHistoryEntry | None:
        return self._history[0] if self._history else None

    @Slot(int)
    def _delete_history(self, index: int) -> None:
        if 0 <= index < len(self._history):
            self._history.pop(index)
            self._rebuild()
            self.changed.emit()

    @Slot()
    def _on_clear_history(self) -> None:
        if not self._history:
            return
        reply = QMessageBox.question(
            self,
            "Очистить историю",
            f"Удалить все записи истории ({len(self._history)})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._history.clear()
            self._rebuild()
            self.changed.emit()

    def _rebuild(self) -> None:
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        has = bool(self._history)
        self._hist_sep.setVisible(has)
        self._history_hdr_row.setVisible(has)
        self._history_scroll.setVisible(has)
        if has:
            self._history_hdr.setText(f"История ({len(self._history)})")
            for i, entry in enumerate(self._history):
                row = HistoryRow(entry, i, self)
                row.delete_requested.connect(self._delete_history)
                self._history_layout.addWidget(row)
