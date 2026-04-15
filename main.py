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
from app.ui.main_window import MainWindow
from app.ui.theme import Theme
from app.core.updater import cleanup_old_exe


APP_VERSION = "0.0.1"


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
