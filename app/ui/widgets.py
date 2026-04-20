"""
Reusable layout primitives and small widget helpers.

Centralizes the helpers that were file-local in settings_widget.py and the
`_h_sep` separator that was duplicated in export_jobs_widget.py. All visual
properties come from `app.ui.theme.Theme` — no hardcoded colors.
"""
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import Theme

type StatusKind = Literal["neutral", "ok", "error", "warning", "info"]


def _apply_light_popup_palette(widget: QWidget) -> None:
    """Force a light palette so Win11 dark-mode doesn't paint a black frame."""
    pal = widget.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(Theme.surface))
    pal.setColor(QPalette.ColorRole.Base, QColor(Theme.surface))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(Theme.gray_50))
    pal.setColor(QPalette.ColorRole.Text, QColor(Theme.gray_900))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(Theme.gray_900))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(Theme.primary_200))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(Theme.primary_900))
    widget.setPalette(pal)


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
    _apply_light_popup_palette(view)
    # The view lives inside a top-level popup window. Disable the OS
    # drop-shadow and force a light palette on the window frame too.
    win = view.window()
    if win is not None and win is not view:
        win.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        _apply_light_popup_palette(win)
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
