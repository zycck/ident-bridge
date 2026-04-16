# -*- coding: utf-8 -*-
"""MainWindow — top-level application shell for iDentBridge."""
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QMainWindow,
    QSystemTrayIcon,
)

from app.config import ConfigManager
from app.core.app_logger import get_logger
from app.ui.main_window_bootstrap import MainWindowBootstrapController
from app.ui.main_window_chrome import MainWindowChromeController
from app.ui.main_window_debug import DebugWindowCoordinator
from app.ui.main_window_lifecycle import (
    MainWindowLifecycleController,
    build_tray,
)
from app.ui.main_window_navigation import MainWindowNavigationController
from app.ui.main_window_pages import build_main_window_pages
from app.ui.main_window_shell import MainWindowShell
from app.ui.main_window_signal_router import MainWindowSignalRouter
from app.ui.update_flow_coordinator import UpdateFlowCoordinator

_log = get_logger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: ConfigManager,
        current_version: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._current_version = current_version
        self._debug = DebugWindowCoordinator(self)

        self._build_ui()
        self._chrome = MainWindowChromeController(
            window=self,
            title_bar=self._title_bar,
        )
        self._chrome.wire()
        self._build_tray()
        self._signal_router = MainWindowSignalRouter(
            dashboard=self._dashboard,
            export_jobs=self._export_jobs,
            update_flow=self._update_flow,
            tray=self._tray,
        )
        self._signal_router.wire()
        self._lifecycle = MainWindowLifecycleController(
            window=self,
            config=self._config,
            tray=self._tray,
            export_jobs=self._export_jobs,
            dashboard=self._dashboard,
            close_debug_window=self._close_debug_window,
        )
        self._bootstrap = MainWindowBootstrapController(
            window=self,
            config=self._config,
            toggle_debug_window=self._toggle_debug_window,
            cleanup=self._cleanup,
            run_update_check=self._run_update_check_silently,
        )
        self._bootstrap.wire()

        _log.info("iDentBridge %s started", current_version)
        self.setWindowTitle("iDentBridge")
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.FramelessWindowHint
        )
        self.resize(900, 600)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        pages = build_main_window_pages(self._config, self._current_version, self)
        self._stack = pages.stack
        self._dashboard = pages.dashboard
        self._export_jobs = pages.export_jobs
        self._settings_widget = pages.settings_widget
        self._shell = MainWindowShell(
            current_version=self._current_version,
            stack=self._stack,
            on_navigate=self.navigate,
            on_debug=self._toggle_debug_window,
            parent=self,
        )
        self.setCentralWidget(self._shell)
        self._title_bar = self._shell.title_bar()
        self._nav_btns = self._shell.nav_buttons()
        self._update_flow = UpdateFlowCoordinator(
            self,
            self._dashboard,
            current_version=self._current_version,
        )
        self._navigation = MainWindowNavigationController(
            stack=self._stack,
            buttons=self._nav_btns,
            normal_icons=self._shell.normal_icons(),
            active_icons=self._shell.active_icons(),
        )

        self.navigate(0)

    # ------------------------------------------------------------------
    # Maximize toggle
    # ------------------------------------------------------------------

    def changeEvent(self, event) -> None:  # type: ignore[override]
        if hasattr(self, "_chrome"):
            self._chrome.handle_change_event(event)
        super().changeEvent(event)

    def _toggle_debug_window(self) -> None:
        self._debug.toggle()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _build_tray(self) -> None:
        self._tray = build_tray(
            self,
            on_open=self._show_window,
            on_check_update=self._run_update_check_silently,
            on_quit=self._quit,
            on_activated=self._on_tray_activated,
        )

    def show_tray_message(self, title: str, msg: str) -> None:
        self._lifecycle.show_tray_message(title, msg)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, index: int) -> None:
        self._navigation.navigate(index)

    # ------------------------------------------------------------------
    # Update flow
    # ------------------------------------------------------------------

    def _run_update_check_silently(self) -> None:
        self._update_flow.run_silent_check()

    # ------------------------------------------------------------------
    # Window / tray events
    # ------------------------------------------------------------------

    def _close_debug_window(self) -> None:
        self._debug.close()

    def _show_window(self) -> None:
        self._lifecycle.show_window()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        self._lifecycle.on_tray_activated(reason)

    def _quit(self) -> None:
        self._lifecycle.quit()

    @Slot()
    def _cleanup(self) -> None:
        self._lifecycle.cleanup()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._lifecycle.handle_close_event(event)
