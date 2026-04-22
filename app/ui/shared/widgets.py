"""
Reusable layout primitives and small widget helpers.

Centralizes the helpers that were file-local in settings_widget.py and the
`_h_sep` separator that was duplicated in export_jobs_widget.py. All visual
properties come from `app.ui.theme.Theme` — no hardcoded colors.
"""
from typing import Literal

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.shared.theme import Theme

type StatusKind = Literal["neutral", "ok", "error", "warning", "info"]


def apply_light_window_palette(
    widget: QWidget,
    *,
    background: str = Theme.surface,
    base: str | None = None,
) -> None:
    """Force a light palette so Win11 dark-mode doesn't paint a black frame."""
    base_color = base or background
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(background))
    pal.setColor(QPalette.ColorRole.Base, QColor(base_color))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(Theme.gray_50))
    pal.setColor(QPalette.ColorRole.Button, QColor(background))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(Theme.gray_900))
    pal.setColor(QPalette.ColorRole.Text, QColor(Theme.gray_900))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(Theme.gray_900))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(Theme.gray_400))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(Theme.primary_200))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(Theme.primary_900))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, QColor(Theme.gray_50))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(Theme.gray_50))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(Theme.gray_500))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(Theme.gray_500))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(Theme.gray_500))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, QColor(Theme.gray_400))
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


def _harden_popup_window(widget: QWidget) -> None:
    widget.setWindowFlags(widget.windowFlags() | Qt.WindowType.NoDropShadowWindowHint)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)


_WINDOW_QSS = (
    f"QDialog {{"
    f"  background-color: {Theme.surface_tinted};"
    f"  color: {Theme.gray_900};"
    f"}}"
)


_POPUP_QSS = (
    f"QListView {{"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_900};"
    f"  border: 1px solid {Theme.border_strong};"
    f"  border-radius: {Theme.radius}px;"
    f"  padding: 4px;"
    f"  outline: 0;"
    f"}}"
    f"QListView::item {{"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_900};"
    f"  padding: 6px 10px;"
    f"  border-radius: {Theme.radius_sm}px;"
    f"  min-height: 22px;"
    f"}}"
    f"QListView::item:hover {{"
    f"  background-color: {Theme.primary_50};"
    f"  color: {Theme.primary_900};"
    f"}}"
    f"QListView::item:selected {{"
    f"  background-color: {Theme.primary_100};"
    f"  color: {Theme.primary_900};"
    f"}}"
)


_MENU_QSS = (
    f"QMenu {{"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_900};"
    f"  border: 1px solid {Theme.border_strong};"
    f"  border-radius: {Theme.radius}px;"
    f"  padding: 6px;"
    f"}}"
    f"QMenu::item {{"
    f"  padding: 7px 12px;"
    f"  border-radius: {Theme.radius_sm}px;"
    f"  background-color: {Theme.surface};"
    f"  color: {Theme.gray_900};"
    f"}}"
    f"QMenu::item:selected {{"
    f"  background-color: {Theme.primary_100};"
    f"  color: {Theme.primary_900};"
    f"}}"
    f"QMenu::separator {{"
    f"  height: 1px;"
    f"  margin: 5px 8px;"
    f"  background-color: {Theme.border};"
    f"}}"
)


def style_menu_popup(menu: QMenu) -> None:
    """Force a light-themed popup menu on Windows and offscreen tests."""
    menu.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    _harden_popup_window(menu)
    menu.setStyleSheet(_MENU_QSS)
    apply_light_window_palette(menu)
    win = menu.window()
    if win is not None and win is not menu:
        _harden_popup_window(win)
        apply_light_window_palette(win)
        win.setStyleSheet(
            f"background-color: {Theme.surface};"
            f"border: 1px solid {Theme.border_strong};"
        )


def style_light_dialog(dialog: QDialog) -> None:
    """Force a light top-level dialog shell even under dark system chrome."""
    _harden_popup_window(dialog)
    apply_light_window_palette(dialog, background=Theme.surface_tinted)
    dialog.setStyleSheet(_WINDOW_QSS)


def style_combo_popup(combo: QComboBox) -> None:
    """
    Force a light-themed, frameless popup for a QComboBox.

    On Windows 11 the QComboBox popup is a top-level window that
    picks up the system's dark Mica / Acrylic frame when the OS is in
    dark mode — even if the app stylesheet paints the internals
    white. The result is a black rectangle around the dropdown. We
    compensate by:

    * clearing the native drop-shadow / translucent-bg flags,
    * overriding the popup window's palette with our light tokens,
    * applying an explicit QSS on the view so the inner list is
      styled even when the global sheet doesn't propagate.

    Call this once after constructing each QComboBox.
    """
    view = combo.view()
    if view is None:
        return
    view.setStyleSheet(_POPUP_QSS)
    apply_light_window_palette(view)
    # The view lives inside a top-level popup window. Disable the OS
    # drop-shadow and force a light palette on the window frame too.
    win = view.window()
    if win is not None and win is not view:
        _harden_popup_window(win)
        apply_light_window_palette(win)
        win.setStyleSheet(
            f"background-color: {Theme.surface};"
            f"border: 1px solid {Theme.border_strong};"
        )


def hsep() -> QFrame:
    """Thin horizontal separator line (replaces ad-hoc `_h_sep` helpers)."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"background-color: {Theme.border}; max-height: 1px; border: none;"
    )
    return sep


def section(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    """QGroupBox section with consistent padding/spacing."""
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setSpacing(8)
    layout.setContentsMargins(12, 14, 12, 12)
    return box, layout


def labeled_row(
    label_text: str, widget: QWidget, label_width: int = 120
) -> QHBoxLayout:
    """Row with a fixed-width left label and an expanding widget."""
    row = QHBoxLayout()
    row.setSpacing(10)
    lbl = QLabel(label_text)
    lbl.setFixedWidth(label_width)
    lbl.setObjectName("rowLabel")
    row.addWidget(lbl)
    row.addWidget(widget, stretch=1)
    return row


def status_label() -> QLabel:
    """Factory for inline status text labels."""
    lbl = QLabel()
    lbl.setObjectName("statusLabel")
    lbl.setWordWrap(True)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return lbl


def set_status(lbl: QLabel, kind: StatusKind, text: str) -> None:
    """Apply a semantic color + text to a status label."""
    color_map: dict[StatusKind, str] = {
        "neutral": Theme.gray_500,
        "ok":      Theme.success,
        "error":   Theme.error,
        "warning": Theme.warning,
        "info":    Theme.info,
    }
    lbl.setStyleSheet(
        f"color: {color_map[kind]}; "
        f"font-size: {Theme.font_size_sm}pt; padding: 2px 0;"
    )
    lbl.setText(text)


class HeaderLabel(QLabel):
    """
    Section header label.

    Has objectName='sectionHeader' so QSS can style it (see theme.qss for the
    sectionHeader rule — bright gray_600, semibold, uppercase, letter-spaced).
    Uses Theme constants for any inline fallback styling so this is safe to use
    even before QSS is loaded.
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionHeader")
        # Inline fallback (will be overridden by QSS once theme.qss applies):
        self.setStyleSheet(
            f"color: {Theme.gray_600}; "
            f"font-size: {Theme.font_size_sm}pt; "
            f"font-weight: {Theme.font_weight_semi}; "
            f"background: transparent; border: none;"
        )


def _spinner_icon(*, color: str, size: int, angle: int) -> QIcon:
    """Build a small circular spinner icon for busy buttons."""
    logical_size = max(10, int(size))
    dpr = 2.0
    pixmap = QPixmap(int(logical_size * dpr), int(logical_size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.6, logical_size / 7.5))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    inset = pen.widthF()
    rect = QRectF(
        inset,
        inset,
        float(logical_size) - (inset * 2.0),
        float(logical_size) - (inset * 2.0),
    )
    painter.drawArc(rect, int(angle * 16), int(270 * 16))
    painter.end()
    return QIcon(pixmap)


class BusyPushButton(QPushButton):
    """Push button with a lightweight rotating spinner state."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        busy_text: str | None = None,
        busy_color: str = Theme.gray_700,
    ) -> None:
        super().__init__(text, parent)
        self._busy = False
        self._busy_angle = 0
        self._busy_color = busy_color
        self._idle_text = text
        self._busy_text = text if busy_text is None else busy_text
        self._idle_icon = QIcon()
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(90)
        self._spinner_timer.timeout.connect(self._advance_spinner)

    def capture_idle_state(self) -> None:
        self._idle_text = self.text()
        self._idle_icon = self.icon()

    def set_busy_text(self, text: str) -> None:
        self._busy_text = text
        if self._busy:
            self.setText(text)

    def set_busy(self, busy: bool) -> None:
        if self._busy == busy:
            return

        self._busy = busy
        if busy:
            self.capture_idle_state()
            self._busy_angle = 0
            self.setText(self._busy_text)
            self._spinner_timer.start()
            self._apply_spinner_icon()
            return

        self._spinner_timer.stop()
        self.setText(self._idle_text)
        self.setIcon(self._idle_icon)

    def is_busy(self) -> bool:
        return self._busy

    def _advance_spinner(self) -> None:
        self._busy_angle = (self._busy_angle + 36) % 360
        self._apply_spinner_icon()

    def _apply_spinner_icon(self) -> None:
        icon_size = self.iconSize().width()
        if icon_size <= 0:
            icon_size = 14
        self.setIcon(
            _spinner_icon(
                color=self._busy_color,
                size=icon_size,
                angle=self._busy_angle,
            )
        )
