# -*- coding: utf-8 -*-
"""iDentBridge — entry point."""
from __future__ import annotations

import signal
import sys
import os
from pathlib import Path
from string import Template

from PySide6.QtWidgets import QApplication

from app.config import ConfigManager
from app.core import app_logger
from app.ui import icons_rc  # noqa: F401  — registers :/icons/check.svg for QSS
from app.ui.main_window import MainWindow
from app.ui.theme import Theme
from app.core.updater import cleanup_old_exe


APP_VERSION = "0.0.1"


def _load_fonts() -> None:
    """
    Register bundled fonts and set Manrope as the application-wide default.

    Manrope is chosen for its excellent Cyrillic glyphs (designed by Russian
    designer Mikhail Sharanda) — Inter's Cyrillic component has known stroke-
    width and metrics issues that look ugly at small UI sizes.

    PreferNoHinting + PreferAntialias produces noticeably smoother rendering
    for non-Latin scripts at small sizes than the default PreferFullHinting,
    which forces grid-aligned pixel alignment that mangles thin Cyrillic
    strokes.
    """
    from PySide6.QtGui import QFont, QFontDatabase

    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "resources" / "fonts"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent / "resources" / "fonts"

    font_path = base / "Manrope.ttf"
    if not font_path.exists():
        # No bundled font — fall through to system Segoe UI Variable (still
        # apply the hinting fix to whatever the system gives us).
        family = "Segoe UI Variable"
    else:
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            family = "Segoe UI Variable"
        else:
            families = QFontDatabase.applicationFontFamilies(font_id)
            family = families[0] if families else "Segoe UI Variable"

    default_font = QFont(family, 9)
    # PreferNoHinting: let DirectWrite do subpixel positioning instead of
    # forcing pixel-grid alignment. Smoother for thin strokes and Cyrillic.
    default_font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    # PreferAntialias: explicit AA even at small sizes.
    default_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)

    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance()
    if qapp is not None:
        qapp.setFont(default_font)


def _load_app_icon(app: QApplication) -> None:
    """Set the application icon for taskbar / window decorations."""
    from PySide6.QtGui import QIcon
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "resources"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent / "resources"
    icon_path = base / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))


def _load_theme() -> str:
    """Return QSS with design tokens substituted, resolving for dev/frozen modes."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundles resources into sys._MEIPASS
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent

    qss_path = base / "resources" / "theme.qss"
    try:
        raw = qss_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    # ${token} placeholders are substituted from Theme.tokens(); files without
    # placeholders pass through unchanged (Phase 1 compat).
    return Template(raw).safe_substitute(Theme.tokens())


def main() -> None:
    # Remove leftover .exe from a previous self-update
    cleanup_old_exe()

    app = QApplication(sys.argv)
    app.setApplicationName("iDentBridge")
    app.setApplicationVersion(APP_VERSION)
    # Don't quit when the main window is closed (tray icon keeps app alive)
    app.setQuitOnLastWindowClosed(False)

    _load_app_icon(app)   # taskbar / window icon

    # Install Qt→Python logging bridge before any UI is created
    app_logger.setup()

    _load_fonts()

    theme = _load_theme()
    if theme:
        app.setStyleSheet(theme)

    # Let Python handle SIGINT (Ctrl+C) instead of Qt suppressing it
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    config = ConfigManager()
    window = MainWindow(config, APP_VERSION)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
