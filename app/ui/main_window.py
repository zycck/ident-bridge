# -*- coding: utf-8 -*-
"""MainWindow — top-level application shell for iDentBridge."""
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.ui.title_bar import CustomTitleBar

from app.config import ConfigManager
from app.core.app_logger import get_logger
from app.ui.dashboard_widget import DashboardWidget
from app.ui.error_dialog import install_global_handler
from app.ui.export_jobs_widget import ExportJobsWidget
from app.ui.main_window_debug import DebugWindowCoordinator
from app.ui.main_window_lifecycle import (
    MainWindowLifecycleController,
    build_tray,
)
from app.ui.main_window_navigation import (
    MainWindowNavigationController,
    build_navigation_sidebar,
)
from app.ui.settings_widget import SettingsWidget
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
        self._build_tray()
        self._lifecycle = MainWindowLifecycleController(
            window=self,
            config=self._config,
            tray=self._tray,
            export_jobs=self._export_jobs,
            dashboard=self._dashboard,
            close_debug_window=self._close_debug_window,
        )
        self._install_exception_hook()
        self._setup_shortcuts()

        # Connect app-level quit signal for proper cleanup
        QApplication.instance().aboutToQuit.connect(self._cleanup)  # type: ignore[union-attr]

        if config.get("auto_update_check"):
            self._run_update_check_silently()

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
        central = QWidget()
        self.setCentralWidget(central)

        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Custom title bar
        self._title_bar = CustomTitleBar("iDentBridge", self)
        self._title_bar.minimize_clicked.connect(self.showMinimized)
        self._title_bar.maximize_clicked.connect(self._toggle_maximize)
        self._title_bar.close_clicked.connect(self.close)
        outer.addWidget(self._title_bar)

        # Body: sidebar + stack
        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        (
            sidebar,
            self._nav_btns,
            nav_icons_normal,
            nav_icons_active,
        ) = build_navigation_sidebar(
            body,
            current_version=self._current_version,
            on_navigate=self.navigate,
            on_debug=self._toggle_debug_window,
        )

        # Stacked pages
        self._stack = QStackedWidget()
        self._dashboard = DashboardWidget(self._config, self)
        self._export_jobs = ExportJobsWidget(self._config, self)
        self._settings_widget = SettingsWidget(
            self._config, self._current_version, self
        )
        self._update_flow = UpdateFlowCoordinator(
            self,
            self._dashboard,
            current_version=self._current_version,
        )
        self._stack.addWidget(self._dashboard)        # index 0
        self._stack.addWidget(self._export_jobs)      # index 1
        self._stack.addWidget(self._settings_widget)  # index 2
        self._navigation = MainWindowNavigationController(
            stack=self._stack,
            buttons=self._nav_btns,
            normal_icons=nav_icons_normal,
            active_icons=nav_icons_active,
        )

        root.addWidget(sidebar)
        root.addWidget(self._stack, stretch=1)

        outer.addWidget(body, stretch=1)

        # Wire update_requested signal from dashboard
        self._dashboard.update_requested.connect(self._on_update_requested)

        # Wire sync results from export jobs → dashboard last sync card
        self._export_jobs.sync_completed.connect(self._dashboard.update_last_sync)
        self._export_jobs.history_changed.connect(self._dashboard.refresh_activity)
        self._export_jobs.failure_alert.connect(self._on_export_failure_alert)

        self.navigate(0)

    # ------------------------------------------------------------------
    # Maximize toggle
    # ------------------------------------------------------------------

    @Slot()
    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._title_bar.update_max_icon(self.isMaximized())

    def changeEvent(self, event) -> None:  # type: ignore[override]
        if event.type() == event.Type.WindowStateChange:
            if hasattr(self, "_title_bar"):
                self._title_bar.update_max_icon(self.isMaximized())
        super().changeEvent(event)

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        debug_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        debug_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        debug_shortcut.activated.connect(self._toggle_debug_window)

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

    @Slot(str, str)
    def _on_update_available(self, version: str, url: str) -> None:
        self._update_flow.on_update_available(version, url)

    @Slot(str)
    def _on_update_requested(self, url: str) -> None:
        self._update_flow.on_update_requested(url)

    @Slot(str)
    def _on_update_downloaded(self, downloaded_path: str) -> None:
        self._update_flow.on_update_downloaded(downloaded_path)

    @Slot()
    def _on_update_download_finished(self) -> None:
        self._update_flow.on_update_download_finished()

    @Slot(str)
    def _on_update_download_error(self, message: str) -> None:
        self._update_flow.on_update_download_error(message)

    @Slot(str, int)
    def _on_export_failure_alert(self, job_name: str, count: int) -> None:
        """Show a tray balloon when an export job fails N times in a row."""
        self._tray.showMessage(
            "iDentBridge — ошибка выгрузки",
            f"«{job_name}» — {count} неудачных запусков подряд. "
            f"Откройте приложение, чтобы посмотреть детали.",
            QSystemTrayIcon.MessageIcon.Warning,
            8000,
        )

    # ------------------------------------------------------------------
    # Error hook
    # ------------------------------------------------------------------

    def _install_exception_hook(self) -> None:
        install_global_handler()

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
