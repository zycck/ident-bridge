# -*- coding: utf-8 -*-
"""
CustomTitleBar — frameless window title bar with drag-to-move and
minimal/maximize/close buttons. Used by MainWindow when the native
Windows title bar is suppressed via FramelessWindowHint.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from app.ui.lucide_icons import lucide
from app.ui.theme import Theme


def _icon_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources" / "icon.ico"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent / "resources" / "icon.ico"


class CustomTitleBar(QFrame):
    """
    Lightweight 32px title bar replacement for FramelessWindowHint windows.

    Provides:
    - app icon + title label on the left
    - minimize / maximize / close buttons on the right
    - drag the bar background to move the window
    - double-click toggles maximized state
    """

    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked    = Signal()

    HEIGHT = 32

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#titleBar {{"
            f"  background-color: {Theme.surface_tinted};"
            f"  border-bottom: 1px solid {Theme.border};"
            f"}}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(8)

        # ── App icon ──────────────────────────────────────────────────
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(16, 16)
        icon_lbl.setStyleSheet("background: transparent;")
        ip = _icon_path()
        if ip.exists():
            icon_lbl.setPixmap(
                QIcon(str(ip)).pixmap(16, 16)
            )
        layout.addWidget(icon_lbl)

        # ── Title label ───────────────────────────────────────────────
        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color: {Theme.gray_700}; "
            f"font-size: {Theme.font_size_base}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent;"
        )
        layout.addWidget(self._title_lbl)
        layout.addStretch()

        # ── Window control buttons ────────────────────────────────────
        self._min_btn = self._make_btn("minus",  Theme.gray_500, hover_bg=Theme.gray_100)
        self._max_btn = self._make_btn("square", Theme.gray_500, hover_bg=Theme.gray_100)
        self._cls_btn = self._make_btn("x",      Theme.gray_500, hover_bg=Theme.error,
                                       hover_color=Theme.surface)

        self._min_btn.setToolTip("Свернуть")
        self._max_btn.setToolTip("Развернуть")
        self._cls_btn.setToolTip("Закрыть")

        self._min_btn.clicked.connect(self.minimize_clicked)
        self._max_btn.clicked.connect(self.maximize_clicked)
        self._cls_btn.clicked.connect(self.close_clicked)

        for b in (self._min_btn, self._max_btn, self._cls_btn):
            layout.addWidget(b)

        # Drag state
        self._drag_pos: QPoint | None = None

    # ------------------------------------------------------------------
    def _make_btn(
        self,
        icon_name: str,
        icon_color: str,
        *,
        hover_bg: str,
        hover_color: str | None = None,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(36, self.HEIGHT)
        btn.setIcon(lucide(icon_name, color=icon_color, size=12))
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  border: none;"
            f"  background: transparent;"
            f"  padding: 0;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {hover_bg};"
            f"}}"
        )
        # Store icons for hover swap (used by close button to go white-on-red)
        btn._icon_default = lucide(icon_name, color=icon_color, size=12)  # type: ignore[attr-defined]
        if hover_color:
            btn._icon_hover = lucide(icon_name, color=hover_color, size=12)  # type: ignore[attr-defined]
            btn.installEventFilter(self)
        return btn

    def eventFilter(self, obj, event):  # noqa: N802
        """Swap close button icon to white on hover (bg turns red)."""
        if hasattr(obj, "_icon_hover"):
            if event.type() == QEvent.Type.Enter:
                obj.setIcon(obj._icon_hover)
            elif event.type() == QEvent.Type.Leave:
                obj.setIcon(obj._icon_default)
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Drag-to-move
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None:
                self._drag_pos = (
                    event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            window = self.window()
            if window is not None and not window.isMaximized():
                window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_clicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    def update_max_icon(self, is_maximized: bool) -> None:
        """Switch maximize button tooltip between restore and maximize state."""
        self._max_btn.setToolTip("Восстановить" if is_maximized else "Развернуть")
