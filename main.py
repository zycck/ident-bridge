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
    """Register bundled fonts with Qt and set Inter Variable as the app default."""
    from PySide6.QtGui import QFont, QFontDatabase

    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS) / "resources" / "fonts"  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent / "resources" / "fonts"

    inter_path = base / "InterVariable.ttf"
    if not inter_path.exists():
        return

    font_id = QFontDatabase.addApplicationFont(str(inter_path))
    if font_id < 0:
        return

    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return
    family = families[0]

    # Set as application-wide default — every widget that doesn't
    # explicitly override its font will pick this up. This is the
    # ONLY reliable way to make inline setStyleSheet font-size labels
    # also use Inter (QSS font-family inheritance is unreliable when
    # children set their own font-size via setStyleSheet).
    default_font = QFont(family, 9)
    default_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    default_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)

    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance()
    if qapp is not None:
        qapp.setFont(default_font)


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
