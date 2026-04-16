"""Helpers for the frameless window title bar."""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton

from app.ui.lucide_icons import lucide


def icon_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources" / "icon.ico"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent / "resources" / "icon.ico"


def make_control_button(
    icon_name: str,
    icon_color: str,
    *,
    hover_bg: str,
    hover_color: str | None = None,
    height: int = 32,
) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(36, height)
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
    btn._icon_default = lucide(icon_name, color=icon_color, size=12)  # type: ignore[attr-defined]
    if hover_color:
        btn._icon_hover = lucide(icon_name, color=hover_color, size=12)  # type: ignore[attr-defined]
    return btn
