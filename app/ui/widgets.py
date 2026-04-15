# -*- coding: utf-8 -*-
"""
Reusable layout primitives and small widget helpers.

Centralizes the helpers that were file-local in settings_widget.py and the
`_h_sep` separator that was duplicated in export_jobs_widget.py. All visual
properties come from `app.ui.theme.Theme` — no hardcoded colors.
"""
from __future__ import annotations

from typing import Literal

from PySide6.QtCore import Qt
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

StatusKind = Literal["neutral", "ok", "error", "warning", "info"]


def style_combo_popup(combo: QComboBox) -> None:
    """
    Strip the Windows default drop-shadow + black frame from a QComboBox
    popup. Qt's stylesheet alone can't override the popup window's native
    decoration — we have to set window flags on the underlying view.

    Call this once after constructing each QComboBox.
    """
    view = combo.view()
    if view is None:
        return
    # The view lives inside a top-level popup window. Disable the OS
    # drop-shadow and any native frame.
    win = view.window()
    if win is not None:
        win.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)


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
