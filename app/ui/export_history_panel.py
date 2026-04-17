"""History panel widget used by ExportJobEditor."""

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.config import ExportHistoryEntry
from app.core.constants import HISTORY_MAX
from app.ui.history_row import HistoryRow
from app.ui.theme import Theme
from app.ui.widgets import hsep


class ExportHistoryPanel(QWidget):
    """Owns export-job history data and its UI rendering.

    The panel mutates history incrementally — ``prepend_entry`` inserts a
    single row at the top and optionally drops the oldest, ``_delete_history``
    removes exactly one row. A full ``_rebuild`` is only used by
    ``set_history`` (initial load from config). This avoids the O(N) widget
    churn that the previous implementation paid on every sync.
    """

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[ExportHistoryEntry] = []
        self._row_widgets: list[HistoryRow] = []
        self._build_ui()
        self._update_chrome()

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
        """Replace the entire history list (full rebuild — use sparingly)."""
        self._history = list(history)
        self._rebuild()

    def prepend_entry(self, entry: ExportHistoryEntry) -> None:
        """Insert one entry at the top; drop the oldest if over the cap."""
        self._history.insert(0, entry)
        row = self._make_row(entry, 0)
        self._history_layout.insertWidget(0, row)
        self._row_widgets.insert(0, row)
        if len(self._history) > HISTORY_MAX:
            overflow = len(self._history) - HISTORY_MAX
            for _ in range(overflow):
                self._history.pop()
                old = self._row_widgets.pop()
                self._history_layout.removeWidget(old)
                old.deleteLater()
        self._reindex_rows()
        self._update_chrome()
        self.changed.emit()

    def latest_entry(self) -> ExportHistoryEntry | None:
        return self._history[0] if self._history else None

    @Slot(int)
    def _delete_history(self, index: int) -> None:
        if 0 <= index < len(self._history):
            self._history.pop(index)
            row = self._row_widgets.pop(index)
            self._history_layout.removeWidget(row)
            row.deleteLater()
            self._reindex_rows()
            self._update_chrome()
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

    # ------------------------------------------------------------------
    # internals

    def _make_row(self, entry: ExportHistoryEntry, index: int) -> HistoryRow:
        row = HistoryRow(entry, index, self)
        row.delete_requested.connect(self._delete_history)
        return row

    def _reindex_rows(self) -> None:
        """Sync each row's ``_index`` with its current layout position.

        ``HistoryRow.delete_requested`` carries an int index — after an
        insert or delete we must refresh every row so subsequent clicks
        target the correct slot.
        """
        for i, r in enumerate(self._row_widgets):
            r._index = i

    def _update_chrome(self) -> None:
        has = bool(self._history)
        self._hist_sep.setVisible(has)
        self._history_hdr_row.setVisible(has)
        self._history_scroll.setVisible(has)
        if has:
            self._history_hdr.setText(f"История ({len(self._history)})")

    def _rebuild(self) -> None:
        """Full teardown + recreate. Only for set_history / clear."""
        while self._history_layout.count():
            item = self._history_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._row_widgets = []

        self._update_chrome()
        for i, entry in enumerate(self._history):
            row = self._make_row(entry, i)
            self._history_layout.addWidget(row)
            self._row_widgets.append(row)
