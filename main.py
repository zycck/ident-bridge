# -*- coding: utf-8 -*-
"""iDentBridge — entry point."""
from __future__ import annotations

import sys
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.config import ConfigManager
from app.ui.main_window import MainWindow
from app.core.updater import cleanup_old_exe


APP_VERSION = "0.0.1"


def _load_theme() -> str:
    """Return QSS content, resolving the path for both dev and frozen modes."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundles resources into sys._MEIPASS
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).parent

    qss_path = base / "resources" / "theme.qss"
    try:
        return qss_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def main() -> None:
    # Remove leftover .exe from a previous self-update
    cleanup_old_exe()

    app = QApplication(sys.argv)
    app.setApplicationName("iDentBridge")
    app.setApplicationVersion(APP_VERSION)

    theme = _load_theme()
    if theme:
        app.setStyleSheet(theme)

    config = ConfigManager()
    window = MainWindow(config, APP_VERSION)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
