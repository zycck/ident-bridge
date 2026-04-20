"""
CustomTitleBar — frameless window title bar with drag-to-move and
minimal/maximize/close buttons. Used by MainWindow when the native
Windows title bar is suppressed via FramelessWindowHint.
"""

from typing import override

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, Signal
from PySide6.QtGui import QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from app.ui.title_bar_controller import TitleBarInteractionController
from app.ui.title_bar_helpers import icon_path, make_control_button
from app.ui.theme import Theme


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
        self._controller = TitleBarInteractionController(
            window_provider=self.window,
            emit_maximize=self.maximize_clicked.emit,
        )
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
        ip = icon_path()
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
        self._min_btn = make_control_button("minus", Theme.gray_500, hover_bg=Theme.gray_100, height=self.HEIGHT)
        self._max_btn = make_control_button("square", Theme.gray_500, hover_bg=Theme.gray_100, height=self.HEIGHT)
        self._cls_btn = make_control_button(
            "x",
            Theme.gray_500,
            hover_bg=Theme.error,
            hover_color=Theme.surface,
            height=self.HEIGHT,
        )
        self._cls_btn.installEventFilter(self)

        self._min_btn.setToolTip("Свернуть")
        self._max_btn.setToolTip("Развернуть")
        self._cls_btn.setToolTip("Закрыть")

        self._min_btn.clicked.connect(self.minimize_clicked)
        self._max_btn.clicked.connect(self.maximize_clicked)
        self._cls_btn.clicked.connect(self.close_clicked)

        for b in (self._min_btn, self._max_btn, self._cls_btn):
            layout.addWidget(b)

    # ------------------------------------------------------------------
    @override
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Swap close button icon to white on hover (bg turns red)."""
        self._controller.handle_event_filter(obj, event)
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Drag-to-move
    # ------------------------------------------------------------------
    @override
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._controller.handle_mouse_press(event):
            super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._controller.handle_mouse_move(event):
            super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._controller.handle_mouse_release(event)
        super().mouseReleaseEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self._controller.handle_mouse_double_click(event):
            super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    def update_max_icon(self, is_maximized: bool) -> None:
        """Switch maximize button tooltip between restore and maximize state."""
        self._max_btn.setToolTip("Восстановить" if is_maximized else "Развернуть")
