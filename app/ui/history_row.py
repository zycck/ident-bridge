# -*- coding: utf-8 -*-
"""
HistoryRow — compact one-line widget for a single export-job run.

Layout: [colored-border-left] [trigger icon] [timestamp] [status text] [× delete]

Trigger types are visually distinguished by:
- left border color
- icon color (matches the border)
- icon glyph (mouse-pointer-click / clock / flask-conical)
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.config import ExportHistoryEntry, TriggerType
from app.core.constants import HISTORY_ROW_HEIGHT
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme


# Each trigger gets: (lucide icon name, accent color, human label)
_TRIGGER_META: dict[TriggerType, tuple[str, str, str]] = {
    TriggerType.MANUAL:    ("mouse-pointer-click", Theme.info,        "Вручную"),
    TriggerType.SCHEDULED: ("clock",               Theme.primary_500, "Авто"),
    TriggerType.TEST:      ("flask-conical",       Theme.gray_500,    "Тест"),
}


class HistoryRow(QWidget):
    """Compact one-line row for a single ExportHistoryEntry."""

    delete_requested = Signal(int)  # index in the parent's history list

    def __init__(
        self,
        entry: ExportHistoryEntry,
        index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._index = index
        self.setFixedHeight(HISTORY_ROW_HEIGHT)

        trigger_str = entry.get("trigger", "manual")
        # Backward-compat: legacy "auto" value maps to scheduled
        if trigger_str == "auto":
            trigger_str = "scheduled"
        try:
            trigger = TriggerType(trigger_str)
        except ValueError:
            trigger = TriggerType.MANUAL
        icon_name, accent, label = _TRIGGER_META[trigger]

        # Colored left border via stylesheet
        self.setStyleSheet(
            f"HistoryRow {{"
            f"  border-left: 3px solid {accent};"
            f"  background: transparent;"
            f"}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(8)

        # ── Trigger icon ──────────────────────────────────────────────
        ico_lbl = QLabel()
        ico_lbl.setPixmap(lucide(icon_name, color=accent, size=12).pixmap(12, 12))
        ico_lbl.setFixedWidth(14)
        ico_lbl.setToolTip(label)
        ico_lbl.setStyleSheet("background: transparent;")
        layout.addWidget(ico_lbl)

        # ── Timestamp ─────────────────────────────────────────────────
        ts_lbl = QLabel(self._format_ts(entry.get("ts", "")))
        ts_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        ts_lbl.setFixedWidth(58)
        layout.addWidget(ts_lbl)

        # ── Status text ──────────────────────────────────────────────
        if entry.get("ok"):
            rows = entry.get("rows", 0)
            text = f"✓  {rows} строк"
            color = Theme.success
            tooltip = ""
        else:
            err = entry.get("err", "Ошибка")
            text = f"✗  {err[:55]}"
            color = Theme.error
            tooltip = err

        st_lbl = QLabel(text)
        st_lbl.setStyleSheet(
            f"color: {color}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        if tooltip:
            st_lbl.setToolTip(tooltip)
        layout.addWidget(st_lbl, stretch=1)

        # ── Delete (×) button ────────────────────────────────────────
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

    @staticmethod
    def _format_ts(ts: str) -> str:
        """HH:MM if today, DD.MM HH:MM if recent, raw otherwise."""
        today = datetime.now().strftime("%Y-%m-%d")
        if ts.startswith(today):
            return ts[11:16]
        if len(ts) >= 16:
            return f"{ts[8:10]}.{ts[5:7]} {ts[11:16]}"
        return ts
