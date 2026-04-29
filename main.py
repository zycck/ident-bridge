"""iDentBridge — entry point."""

import signal
import sys
from pathlib import Path
from string import Template
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from app.config import ConfigManager
from app.core import app_logger
from app.core import startup as autostart
from app.core.app_logger import get_logger
from app.core.constants import APP_NAME, APP_VERSION
from app.ui import icons_rc  # noqa: F401  — registers :/icons/check.svg for QSS
from app.ui.main_window import MainWindow
from app.ui.theme import Theme
from app.core.updater import cleanup_old_exe

_log = get_logger(__name__)


def _is_hidden_start() -> bool:
    """True if launched by Windows autostart (registry value carries --hidden)."""
    return autostart.HIDDEN_FLAG in sys.argv[1:]


def _show_main_window_or_stay_in_tray(
    app: QApplication,
    window: MainWindow,
    config: ConfigManager,
) -> None:
    """Skip showing the main window when launched hidden by Windows autostart.

    Falls back to a normal show() if the system tray is unavailable so the
    user is never left without a way to interact with the app.
    """
    del app  # kept for future hooks (focus, geometry, etc.)
    if not _is_hidden_start() or not QSystemTrayIcon.isSystemTrayAvailable():
        window.show()
        return

    _log.info("Hidden autostart: window stays hidden, tray icon only")
    cfg = config.load()
    if cfg.get("tray_autostart_notice_shown"):
        return

    def _notify() -> None:
        tray = getattr(window, "_tray", None)
        if tray is None or not tray.isVisible():
            return
        tray.showMessage(
            "iDentBridge запущен в трее",
            "Приложение работает в фоне. "
            "Кликните по иконке в трее, чтобы открыть окно.",
            QSystemTrayIcon.MessageIcon.Information,
            7000,
        )
        config.update(tray_autostart_notice_shown=True)

    QTimer.singleShot(1500, _notify)


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

    # Silently migrate older autostart entries (without --hidden) so that
    # users upgrading from earlier versions get the new tray-only behavior
    # without having to toggle the setting off and on again.
    try:
        autostart.ensure_hidden_flag()
    except Exception:  # noqa: BLE001
        pass

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
    _show_main_window_or_stay_in_tray(app, window, config)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
