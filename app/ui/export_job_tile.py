"""Presentation tile for a single export job."""

import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QVBoxLayout, QWidget

from app.config import ExportJob
from app.ui.export_job_tile_presenter import build_export_job_tile_display
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
        display = build_export_job_tile_display(self._job)
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

        self._name_lbl = QLabel(display.name)
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
        self._status_lbl = QLabel(display.status_text)
        self._status_lbl.setStyleSheet(
            f"color: {display.status_color}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"background: transparent;"
        )
        layout.addWidget(self._status_lbl)

        layout.addStretch()

        # ── Bottom row: schedule info + more menu ────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        self._sched_lbl = QLabel(display.schedule_text)
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
        display = build_export_job_tile_display(job)
        self._name_lbl.setText(display.name)
        self._status_lbl.setText(display.status_text)
        self._status_lbl.setStyleSheet(
            f"color: {display.status_color}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"background: transparent;"
        )
        self._sched_lbl.setText(display.schedule_text)

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
