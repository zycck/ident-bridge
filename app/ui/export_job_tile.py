# -*- coding: utf-8 -*-
"""Presentation tile for a single export job."""

import uuid
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from app.config import ExportJob
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme


class ExportJobTile(QFrame):
    """Compact tile representing one export job in the list view.

    The whole tile surface is clickable: click → opens the detail editor
    via open_requested signal. The [▶] run button triggers the export
    immediately without opening the editor. The [···] menu offers
    Открыть / Удалить.
    """

    open_requested = Signal(str)   # job_id
    run_requested = Signal(str)    # job_id
    delete_requested = Signal(str)  # job_id

    TILE_W = 280
    TILE_H = 130

    def __init__(self, job: ExportJob, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("jobTile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(self.TILE_W, self.TILE_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._job_id: str = job.get("id", "") or str(uuid.uuid4())
        self._job: ExportJob = job
        self._build_ui()

    def _build_ui(self) -> None:
        # Tile background + hover via inline stylesheet
        self.setStyleSheet(
            f"#jobTile {{"
            f"  background: {Theme.surface};"
            f"  border: 1px solid {Theme.border};"
            f"  border-radius: {Theme.radius_md}px;"
            f"}}"
            f"#jobTile:hover {{"
            f"  border-color: {Theme.primary_400};"
            f"  background: {Theme.primary_50};"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 12, 12)
        layout.setSpacing(6)

        # ── Top row: name + run button ──────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        name = self._job.get("name") or "Без названия"
        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet(
            f"color: {Theme.gray_900}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent;"
        )
        self._name_lbl.setMaximumWidth(self.TILE_W - 60)
        top.addWidget(self._name_lbl, stretch=1)

        self._run_btn = QPushButton()
        self._run_btn.setIcon(lucide("play", color=Theme.gray_900, size=12))
        self._run_btn.setObjectName("primaryBtn")
        self._run_btn.setFixedSize(28, 28)
        self._run_btn.setToolTip("Запустить сейчас")
        self._run_btn.clicked.connect(self._on_run_clicked)
        top.addWidget(self._run_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(top)

        # ── Status line: last run summary ────────────────────────────
        status_text, status_color = self._compute_status()
        self._status_lbl = QLabel(status_text)
        self._status_lbl.setStyleSheet(
            f"color: {status_color}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"background: transparent;"
        )
        layout.addWidget(self._status_lbl)

        layout.addStretch()

        # ── Bottom row: schedule info + more menu ────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        sched_text = self._compute_schedule_text()
        self._sched_lbl = QLabel(sched_text)
        self._sched_lbl.setStyleSheet(
            f"color: {Theme.gray_500}; "
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent;"
        )
        bottom.addWidget(self._sched_lbl, stretch=1)

        self._more_btn = QPushButton()
        self._more_btn.setIcon(lucide("ellipsis", color=Theme.gray_500, size=14))
        self._more_btn.setFixedSize(24, 24)
        self._more_btn.setStyleSheet(
            "QPushButton {"
            "  border: 1px solid transparent;"
            "  background: transparent;"
            "  border-radius: 5px;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.gray_100};"
            f"  border-color: {Theme.border};"
            f"}}"
        )
        self._more_btn.setToolTip("Действия")
        self._more_btn.clicked.connect(self._show_menu)
        bottom.addWidget(self._more_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(bottom)

    def job_id(self) -> str:
        return self._job_id

    def update_from_job(self, job: ExportJob) -> None:
        """Refresh the tile's labels from a (possibly updated) job dict."""
        self._job = job
        self._name_lbl.setText(job.get("name") or "Без названия")
        status_text, status_color = self._compute_status()
        self._status_lbl.setText(status_text)
        self._status_lbl.setStyleSheet(
            f"color: {status_color}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"background: transparent;"
        )
        self._sched_lbl.setText(self._compute_schedule_text())

    def _compute_status(self) -> tuple[str, str]:
        """Return (text, color) for the status line based on history[0]."""
        history = self._job.get("history") or []
        if not history:
            return "Ещё не запускалось", Theme.gray_500
        latest = history[0]
        ts_short = self._format_short_ts(latest.get("ts", ""))
        if latest.get("ok"):
            return f"✓ {latest.get('rows', 0)} строк · {ts_short}", Theme.success
        err = latest.get("err", "Ошибка")
        return f"✗ {err[:40]}", Theme.error

    def _compute_schedule_text(self) -> str:
        if not self._job.get("schedule_enabled"):
            return "Ручной запуск"
        mode = self._job.get("schedule_mode", "daily")
        value = self._job.get("schedule_value", "")
        if not value:
            return "Расписание не настроено"
        if mode == "daily":
            return f"Ежедневно в {value}"
        if mode == "hourly":
            return f"Каждые {value} ч"
        if mode == "minutely":
            return f"Каждые {value} мин"
        if mode == "secondly":
            return f"Каждые {value} с"
        return f"Расписание: {mode}"

    @staticmethod
    def _format_short_ts(ts: str) -> str:
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
        today = datetime.now().date()
        time_str = dt.strftime("%H:%M:%S")
        if dt.date() == today:
            return f"сегодня {time_str}"
        if dt.date() == today - timedelta(days=1):
            return f"вчера {time_str}"
        return f"{dt.strftime('%d.%m')} {time_str}"

    def _on_run_clicked(self) -> None:
        self.run_requested.emit(self._job_id)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        open_act = menu.addAction("Открыть")
        del_act = menu.addAction("Удалить")
        chosen = menu.exec(self._more_btn.mapToGlobal(self._more_btn.rect().bottomLeft()))
        if chosen is open_act:
            self.open_requested.emit(self._job_id)
        elif chosen is del_act:
            self.delete_requested.emit(self._job_id)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # Open the editor when the tile background is clicked, but not
        # when one of the inner buttons is clicked (Qt routes button
        # presses to the button, not here, so this is mostly redundant).
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if not isinstance(child, QPushButton):
                self.open_requested.emit(self._job_id)
                return
        super().mousePressEvent(event)
