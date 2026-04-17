"""iDentBridge — entry point."""

import signal
import sys
from pathlib import Path
from string import Template
from PySide6.QtWidgets import QApplication

from app.config import ConfigManager
from app.core import app_logger
from app.core.constants import APP_NAME, APP_VERSION
from app.ui import icons_rc  # noqa: F401  — registers :/icons/check.svg for QSS
from app.ui.main_window import MainWindow
from app.ui.theme import Theme
from app.core.updater import cleanup_old_exe


def _set_windows_app_user_model_id() -> None:
    """Tell Windows that this process belongs to its own application.

    Without an explicit AppUserModelID, Windows groups the process
    under whatever spawned it (``python.exe`` when run from source)
    and the taskbar icon / Task Manager "Name" column inherit from
    the parent. A unique AUMID lets Windows associate the process
    with the app's own icon + window title grouping.

    Safe no-op on non-Windows and if the call fails for any reason.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # "CompanyName.ProductName.Subproduct.Version" per MS guidelines.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"iDentBridge.Desktop.{APP_VERSION}"
        )
    except Exception:
        # Feature is cosmetic — never fail app startup over it.
        pass


def _load_fonts(app: QApplication) -> None:
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

    app.setFont(default_font)


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

    # Tag the process BEFORE the QApplication exists, otherwise the
    # first taskbar icon and window-grouping association is already
    # bound to the generic "python.exe" AUMID.
    _set_windows_app_user_model_id()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    # Don't quit when the main window is closed (tray icon keeps app alive)
    app.setQuitOnLastWindowClosed(False)

    _load_app_icon(app)   # taskbar / window icon

    # Install Qt→Python logging bridge before any UI is created
    app_logger.setup()

    _load_fonts(app)

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
