# -*- coding: utf-8 -*-
"""
HistoryRow — compact one-line widget for a single export-job run.

Layout: [colored-border-left] [trigger icon] [timestamp] [status text] [× delete]

Trigger types are visually distinguished by:
- left border color
- icon color (matches the border)
- icon glyph (mouse-pointer-click / clock / flask-conical)
"""
from datetime import datetime, timedelta

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from app.config import ExportHistoryEntry, TriggerType
from app.core.constants import HISTORY_ROW_HEIGHT
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme


def _make_small_font(point_size: float = 8.5) -> QFont:
    """Slightly smaller font that still inherits the app's Inter family."""
    f = QFont()  # picks up QApplication default
    f.setPointSizeF(point_size)
    return f


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
        *,
        job_name: str | None = None,
        show_delete: bool = True,
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
        st_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        st_lbl.setFont(_make_small_font(8.5))
        if tooltip:
            st_lbl.setToolTip(tooltip)
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

    @staticmethod
    def _format_ts(ts: str) -> str:
        """
        Format the stored ts string for display.
        Today          → "Сегодня HH:MM:SS"
        Yesterday      → "Вчера HH:MM:SS"
        Earlier this y → "DD.MM HH:MM:SS"
        Older          → "DD.MM.YY HH:MM:SS"
        Handles both 19-char (new, with seconds) and 16-char (legacy) timestamps.
        """
        if not ts or len(ts) < 16:
            return ts
        dt = None
        for fmt, length in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16)):
            if len(ts) >= length:
                try:
                    dt = datetime.strptime(ts[:length], fmt)
                    break
                except ValueError:
                    pass
        if dt is None:
            return ts
        now = datetime.now()
        today = now.date()
        time_str = dt.strftime("%H:%M:%S")
        if dt.date() == today:
            return f"Сегодня {time_str}"
        if dt.date() == today - timedelta(days=1):
            return f"Вчера {time_str}"
        if dt.year == now.year:
            return f"{dt.strftime('%d.%m')} {time_str}"
        return f"{dt.strftime('%d.%m.%y')} {time_str}"
