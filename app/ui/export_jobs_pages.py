# -*- coding: utf-8 -*-
"""Page widgets used by ExportJobsWidget."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.export_job_tile import ExportJobTile
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme
from app.ui.widgets import hsep


class ExportJobsTilesPage(QWidget):
    """Owns the tiles page scaffold and responsive grid layout."""

    add_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tiles: list[QWidget] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setObjectName("exportToolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        tb.setSpacing(8)

        title = QLabel("Выгрузки")
        title.setStyleSheet(
            f"font-size: {Theme.font_size_lg}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"color: {Theme.gray_900};"
        )
        tb.addWidget(title)
        tb.addStretch()

        add_btn = QPushButton("  Добавить")
        add_btn.setObjectName("primaryBtn")
        add_btn.setIcon(lucide("plus", color=Theme.gray_900, size=14))
        add_btn.setFixedHeight(28)
        add_btn.clicked.connect(self.add_requested)
        tb.addWidget(add_btn)

        layout.addWidget(toolbar)
        layout.addWidget(hsep())

        self._grid_scroll = QScrollArea()
        self._grid_scroll.setWidgetResizable(True)
        self._grid_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._grid_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._grid_scroll.viewport().installEventFilter(self)
        layout.addWidget(self._grid_scroll, stretch=1)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        self._grid_scroll.setWidget(self._grid_container)

        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setContentsMargins(16, 16, 16, 16)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self._empty_lbl = QLabel(
            "Нет настроенных выгрузок.\nНажмите «Добавить» чтобы создать первую."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color: {Theme.gray_400}; "
            f"font-size: {Theme.font_size_md}pt; "
            f"padding: 48px 0;"
        )
        self._grid_layout.addWidget(self._empty_lbl, 0, 0)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._grid_scroll.viewport() and event.type() == event.Type.Resize:
            self.reflow_tiles()
        return super().eventFilter(obj, event)

    def add_tile(self, tile: QWidget) -> None:
        self._tiles.append(tile)
        self._grid_layout.addWidget(tile, len(self._tiles) - 1, 0)
        self.refresh_empty()

    def remove_tile(self, job_id: str) -> QWidget | None:
        for tile in list(self._tiles):
            tile_job_id = getattr(tile, "job_id", lambda: None)()
            if tile_job_id == job_id:
                self._tiles.remove(tile)
                self._grid_layout.removeWidget(tile)
                self.refresh_empty()
                return tile
        return None

    def tiles(self) -> list[QWidget]:
        return list(self._tiles)

    def refresh_empty(self) -> None:
        self._empty_lbl.setVisible(len(self._tiles) == 0)

    def reflow_tiles(self) -> None:
        if not self._tiles:
            return
        viewport_w = self._grid_scroll.viewport().width()
        avail = viewport_w - 32
        spacing = self._grid_layout.spacing()
        cols = max(
            1,
            (avail + spacing) // (ExportJobTile.TILE_W + spacing),
        )
        for tile in self._tiles:
            self._grid_layout.removeWidget(tile)
        for idx, tile in enumerate(self._tiles):
            row, col = divmod(idx, int(cols))
            self._grid_layout.addWidget(tile, row, col)


class ExportJobsEditorPage(QWidget):
    """Owns the editor page scaffold and per-job editor stack."""

    back_requested = Signal()
    delete_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor_scrolls: dict[str, QScrollArea] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setObjectName("exportToolbar")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 8, 16, 8)
        tb.setSpacing(8)

        back_btn = QPushButton("  Назад к списку")
        back_btn.setIcon(lucide("arrow-left", color=Theme.gray_700, size=14))
        back_btn.setFixedHeight(28)
        back_btn.setStyleSheet(
            "QPushButton {"
            f"  border: 1px solid transparent;"
            f"  background: transparent;"
            f"  color: {Theme.gray_700};"
            f"  padding: 0 10px;"
            f"  border-radius: 5px;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.gray_100};"
            f"}}"
        )
        back_btn.clicked.connect(self.back_requested)
        tb.addWidget(back_btn)
        tb.addStretch()

        del_btn = QPushButton("  Удалить выгрузку")
        del_btn.setIcon(lucide("trash-2", color=Theme.error, size=14))
        del_btn.setFixedHeight(28)
        del_btn.setStyleSheet(
            "QPushButton {"
            f"  border: 1px solid transparent;"
            f"  background: transparent;"
            f"  color: {Theme.error};"
            f"  padding: 0 10px;"
            f"  border-radius: 5px;"
            "}"
            f"QPushButton:hover {{"
            f"  background-color: {Theme.error_bg};"
            f"  border-color: {Theme.error};"
            f"}}"
        )
        del_btn.clicked.connect(self.delete_requested)
        tb.addWidget(del_btn)

        layout.addWidget(toolbar)
        layout.addWidget(hsep())

        self._editor_stack = QStackedWidget()
        layout.addWidget(self._editor_stack, stretch=1)

    def add_editor(self, job_id: str, scroll: QScrollArea) -> None:
        self._editor_stack.addWidget(scroll)
        self._editor_scrolls[job_id] = scroll

    def remove_editor(self, job_id: str) -> QScrollArea | None:
        scroll = self._editor_scrolls.pop(job_id, None)
        if scroll is not None:
            self._editor_stack.removeWidget(scroll)
        return scroll

    def show_editor(self, job_id: str) -> bool:
        scroll = self._editor_scrolls.get(job_id)
        if scroll is None:
            return False
        self._editor_stack.setCurrentWidget(scroll)
        return True

    def editor_count(self) -> int:
        return self._editor_stack.count()
