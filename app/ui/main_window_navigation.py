"""Navigation shell helpers extracted from MainWindow."""

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from app.core.constants import NAV_SIDEBAR_W
from app.ui.lucide_icons import lucide
from app.ui.theme import Theme

_NAV_LABELS = ("Статус", "Выгрузки", "Настройки")
_NAV_LUCIDE_ICONS = ("bar-chart-3", "upload-cloud", "settings")


def build_navigation_sidebar(
    parent: QWidget | None,
    *,
    current_version: str,
    on_navigate: Callable[[int], None],
    on_debug: Callable[[], None],
) -> tuple[QWidget, list[QPushButton], list[QIcon], list[QIcon]]:
    sidebar = QWidget(parent)
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(NAV_SIDEBAR_W)
    nav_layout = QVBoxLayout(sidebar)
    nav_layout.setContentsMargins(8, 16, 8, 16)
    nav_layout.setSpacing(4)

    nav_btns: list[QPushButton] = []
    nav_icons_normal: list[QIcon] = []
    nav_icons_active: list[QIcon] = []

    for i, (label, name) in enumerate(zip(_NAV_LABELS, _NAV_LUCIDE_ICONS)):
        icon_n = lucide(name, color=Theme.gray_500)
        icon_a = lucide(name, color=Theme.primary_500)
        nav_icons_normal.append(icon_n)
        nav_icons_active.append(icon_a)
        btn = QPushButton(f"  {label}")
        btn.setObjectName("navBtn")
        btn.setIcon(icon_n)
        btn.clicked.connect(lambda checked=False, idx=i: on_navigate(idx))
        nav_layout.addWidget(btn)
        nav_btns.append(btn)
    nav_layout.addStretch()

    debug_btn = QPushButton("  Debug")
    debug_btn.setObjectName("navBtn")
    debug_btn.setIcon(lucide("bug", color=Theme.gray_500))
    debug_btn.setToolTip("Панель отладки (Ctrl+D)")
    debug_btn.clicked.connect(on_debug)
    nav_layout.addWidget(debug_btn)

    footer_lbl = QLabel(
        f'<span style="color: {Theme.gray_400};">v{current_version}</span>'
        f'  ·  '
        f'<a href="https://t.me/zycck" '
        f'style="color: {Theme.primary_700}; text-decoration: none;">@zycck</a>'
    )
    footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    footer_lbl.setOpenExternalLinks(True)
    footer_lbl.setStyleSheet(
        f"font-size: {Theme.font_size_xs}pt; "
        f"background: transparent; "
        f"padding: 8px 4px;"
    )
    footer_lbl.setToolTip("Связаться с разработчиком в Telegram")
    nav_layout.addWidget(footer_lbl)
    return sidebar, nav_btns, nav_icons_normal, nav_icons_active


class MainWindowNavigationController(QObject):
    def __init__(
        self,
        *,
        stack: QStackedWidget,
        buttons: list[QPushButton],
        normal_icons: list[QIcon],
        active_icons: list[QIcon],
    ) -> None:
        super().__init__(stack)
        self._stack = stack
        self._buttons = buttons
        self._normal_icons = normal_icons
        self._active_icons = active_icons

    def navigate(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._buttons):
            active = i == index
            btn.setObjectName("navBtnActive" if active else "navBtn")
            btn.setIcon(self._active_icons[i] if active else self._normal_icons[i])
            btn.style().unpolish(btn)
            btn.style().polish(btn)
