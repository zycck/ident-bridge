# -*- coding: utf-8 -*-
"""Compact one-line widget for a single export-job run."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.config import ExportHistoryEntry
from app.core.constants import HISTORY_ROW_HEIGHT
from app.ui.history_row_presenter import build_history_row_display
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme


def _make_small_font(point_size: float = 8.5) -> QFont:
    """Slightly smaller font that still inherits the app's Inter family."""
    f = QFont()  # picks up QApplication default
    f.setPointSizeF(point_size)
    return f


class HistoryRow(QWidget):
    """Compact one-line row for a single ExportHistoryEntry."""

    delete_requested = Signal(int)  # index in the parent's history list

    def __init__(
        self,
        entry: ExportHistoryEntry,
        index: int,
        parent: QWidget | None = None,
        *,
        job_name: str | None = None,
        show_delete: bool = True,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self.setFixedHeight(HISTORY_ROW_HEIGHT)
        display = build_history_row_display(entry)

        # Colored left border via stylesheet
        self.setStyleSheet(
            f"HistoryRow {{"
            f"  border-left: 3px solid {display.accent_color};"
            f"  background: transparent;"
            f"}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(8)

        # ── Trigger icon ──────────────────────────────────────────────
        ico_lbl = QLabel()
        ico_lbl.setPixmap(
            lucide(display.icon_name, color=display.accent_color, size=12).pixmap(12, 12)
        )
        ico_lbl.setFixedWidth(14)
        ico_lbl.setToolTip(display.trigger_label)
        ico_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(ico_lbl)

        # ── Timestamp ─────────────────────────────────────────────────
        ts_lbl = QLabel(display.timestamp_text)
        ts_lbl.setStyleSheet(f"color: {Theme.gray_500}; background: transparent;")
        small_font = _make_small_font(8.5)
        ts_lbl.setFont(small_font)
        # Width must fit "Сегодня HH:MM" rendered in the actual font we're
        # using (Manrope at 8.5pt is wider than Inter/Segoe). Measure with
        # QFontMetrics on the explicit font, not on the label's pre-show
        # font which may still be the Qt default.
        fm = QFontMetrics(small_font)
        ts_lbl.setFixedWidth(fm.horizontalAdvance("Сегодня 00:00:00") + 12)
        layout.addWidget(ts_lbl)

        # ── Job name (only when shown in aggregated view) ─────────────
        if job_name is not None:
            name_lbl = QLabel(job_name or "—")
            name_lbl.setStyleSheet(
                f"color: {Theme.gray_700}; "
                f"font-weight: {Theme.font_weight_medium}; "
                f"background: transparent;"
            )
            name_lbl.setFont(_make_small_font(8.5))
            name_lbl.setMinimumWidth(80)
            name_lbl.setMaximumWidth(180)
            layout.addWidget(name_lbl)

        # ── Status text ──────────────────────────────────────────────
        st_lbl = QLabel(display.status_text)
        st_lbl.setStyleSheet(f"color: {display.status_color}; background: transparent;")
        st_lbl.setFont(_make_small_font(8.5))
        if display.status_tooltip:
            st_lbl.setToolTip(display.status_tooltip)
        layout.addWidget(st_lbl, stretch=1)

        # ── Delete (×) button ────────────────────────────────────────
        if show_delete:
            del_btn = QPushButton()
            del_btn.setIcon(lucide("x", color=Theme.gray_400, size=10))
            del_btn.setFixedSize(18, 18)
            del_btn.setFlat(True)
            del_btn.setStyleSheet(
                "QPushButton {"
                "  border: none; background: transparent; padding: 0;"
                "}"
                f"QPushButton:hover {{"
                f"  background-color: {Theme.error_bg};"
                f"  border-radius: 9px;"
                f"}}"
            )
            del_btn.setToolTip("Удалить запись")
            del_btn.clicked.connect(lambda: self.delete_requested.emit(self._index))
            layout.addWidget(del_btn)
