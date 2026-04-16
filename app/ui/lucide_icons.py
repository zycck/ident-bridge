# -*- coding: utf-8 -*-
"""
Lucide SVG icon helper.

Loads SVG files from resources/icons/lucide/, replaces `currentColor`
with the requested color, renders to a hi-DPI QPixmap, and returns a
QIcon. Cached by (name, color, size) to keep recolored variants warm.
"""
import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui.theme import Theme


def _icons_dir() -> Path:
    """Resolve the icons directory for both dev and PyInstaller-frozen modes."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources" / "icons" / "lucide"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent / "resources" / "icons" / "lucide"


@lru_cache(maxsize=128)
def _read_svg(name: str) -> str:
    path = _icons_dir() / f"{name}.svg"
    if not path.exists():
        raise FileNotFoundError(f"Lucide icon not found: {name} (looked in {path})")
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=512)
def lucide(name: str, color: str = Theme.gray_700, size: int = 18) -> QIcon:
    """
    Load a Lucide icon, recolor its stroke (and any explicit currentColor
    fill), and return a hi-DPI QIcon.

    Cached by (name, color, size) so repeated calls with identical args
    return the same QIcon instance.
    """
    svg_text = _read_svg(name)
    colored = (
        svg_text
        .replace('stroke="currentColor"', f'stroke="{color}"')
        .replace('fill="currentColor"',   f'fill="{color}"')
    )
    renderer = QSvgRenderer(QByteArray(colored.encode("utf-8")))

    # Hi-DPI: render at 2x logical size, mark dpr=2 on the pixmap
    dpr = 2.0
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0.0, 0.0, float(size), float(size)))
    painter.end()

    return QIcon(pixmap)
