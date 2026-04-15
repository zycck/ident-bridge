# -*- coding: utf-8 -*-
"""MainWindow — top-level application shell for iDentBridge."""
from __future__ import annotations

from PySide6.QtCore import QThread, Slot
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.config import ConfigManager, IExporter, INotifier
from app.core.app_logger import get_logger
from app.core.scheduler import SyncScheduler
from app.core.telegram import TelegramNotifier
from app.core.updater import GITHUB_REPO, download_and_apply
from app.core.webhook import SheetsWebhook
from app.ui.dashboard_widget import DashboardWidget
from app.ui.debug_window import DebugWindow
from app.ui.error_dialog import install_global_handler
from app.ui.export_widget import ExportWidget
from app.ui.settings_widget import SettingsWidget
from app.workers.update_worker import UpdateWorker

_log = get_logger(__name__)


_NAV_LABELS = ("Статус", "Выгрузка", "Настройки")


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

        # Notifier / exporter
        tg_token = config.get("tg_token")
        tg_chat = config.get("tg_chat_id")
        self._notifier: INotifier | None = (
            TelegramNotifier(tg_token, tg_chat)
            if tg_token and tg_chat
            else None
        )
        self._exporter: IExporter = SheetsWebhook()

        # Scheduler (created before widgets so dashboard can connect)
        self._scheduler = SyncScheduler(self)

        # Debug window — created lazily on first Ctrl+D press
        self._debug_window: DebugWindow | None = None
        # Strong ref to update worker — GC kills workers without explicit Python reference
        self._update_worker: object | None = None

        self._build_ui()
        self._build_tray()
        self._setup_scheduler()
        self._install_exception_hook()
        self._setup_shortcuts()

        # Connect app-level quit signal for proper cleanup
        QApplication.instance().aboutToQuit.connect(self._cleanup)  # type: ignore[union-attr]

        if config.get("auto_update_check") != "False":
            self._run_update_check_silently()

        _log.info("iDentBridge %s started", current_version)
        self.setWindowTitle("iDentBridge")
        self.resize(900, 600)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(168)
        nav_layout = QVBoxLayout(sidebar)
        nav_layout.setContentsMargins(8, 16, 8, 16)
        nav_layout.setSpacing(4)

        self._nav_btns: list[QPushButton] = []
        for i, label in enumerate(_NAV_LABELS):
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.clicked.connect(lambda checked=False, idx=i: self.navigate(idx))
            nav_layout.addWidget(btn)
            self._nav_btns.append(btn)
        nav_layout.addStretch()

        debug_btn = QPushButton("Debug")
        debug_btn.setObjectName("navBtn")
        debug_btn.setToolTip("Панель отладки (Ctrl+D)")
        debug_btn.clicked.connect(self._toggle_debug_window)
        nav_layout.addWidget(debug_btn)

        # Stacked pages
        self._stack = QStackedWidget()
        self._dashboard = DashboardWidget(self._scheduler, self._config, self)
        self._export_widget = ExportWidget(
            self._config, self._exporter, self._notifier, self
        )
        self._settings_widget = SettingsWidget(
            self._config, self._current_version, self
        )
        self._stack.addWidget(self._dashboard)       # index 0
        self._stack.addWidget(self._export_widget)   # index 1
        self._stack.addWidget(self._settings_widget) # index 2

        root.addWidget(sidebar)
        root.addWidget(self._stack, stretch=1)

        # Wire update_requested signal from dashboard
        self._dashboard.update_requested.connect(self._on_update_requested)

        self.navigate(0)

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        from PySide6.QtCore import Qt
        debug_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        debug_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        debug_shortcut.activated.connect(self._toggle_debug_window)

    def _toggle_debug_window(self) -> None:
        if self._debug_window is None:
            self._debug_window = DebugWindow(parent=None)
        if self._debug_window.isVisible():
            self._debug_window.hide()
        else:
            self._debug_window.show()
            self._debug_window.raise_()

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _build_tray(self) -> None:
        self._tray = QSystemTrayIcon(QIcon(), self)
        self._tray.setToolTip("iDentBridge")

        menu = QMenu()
        menu.addAction("Открыть", self._show_window)
        menu.addSeparator()
        menu.addAction("Выгрузить сейчас", self._export_widget._start_export)
        menu.addAction("Проверить обновление", self._run_update_check_silently)
        menu.addSeparator()
        menu.addAction("Выход", self._quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def show_tray_message(self, title: str, msg: str) -> None:
        self._tray.showMessage(
            title, msg, QSystemTrayIcon.MessageIcon.Information, 8000
        )

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def navigate(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_btns):
            btn.setObjectName("navBtnActive" if i == index else "navBtn")
            # Force QSS re-evaluation after objectName change
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def _setup_scheduler(self) -> None:
        cfg = self._config.load()
        mode = cfg.get("schedule_mode") or "daily"
        value = cfg.get("schedule_value") or ""
        if cfg.get("schedule_enabled") and value:
            self._scheduler.configure(mode, value)  # type: ignore[arg-type]
            self._scheduler.start()
        self._scheduler.trigger.connect(self._export_widget._start_export)

    # ------------------------------------------------------------------
    # Update flow
    # ------------------------------------------------------------------

    def _run_update_check_silently(self) -> None:
        worker = UpdateWorker(
            current_version=self._current_version,
            repo=GITHUB_REPO,
        )
        self._update_worker = worker  # keep alive — GC would delete it otherwise
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.check)
        worker.update_available.connect(self._on_update_available)
        worker.update_available.connect(thread.quit)
        worker.no_update.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: setattr(self, '_update_worker', None))

        thread.start()

    @Slot(str, str)
    def _on_update_available(self, version: str, url: str) -> None:
        self.show_tray_message(
            "Доступно обновление",
            f"Версия {version} готова к установке.",
        )
        self._dashboard.show_update_banner(version, url)

    @Slot(str)
    def _on_update_requested(self, url: str) -> None:
        download_and_apply(url)

    # ------------------------------------------------------------------
    # Error hook
    # ------------------------------------------------------------------

    def _install_exception_hook(self) -> None:
        install_global_handler(self._notifier)

    # ------------------------------------------------------------------
    # Window / tray events
    # ------------------------------------------------------------------

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _quit(self) -> None:
        QApplication.quit()

    @Slot()
    def _cleanup(self) -> None:
        """Called by aboutToQuit — stop background services before exit."""
        _log.info("Shutting down…")
        self._scheduler.stop()
        if self._debug_window is not None:
            self._debug_window.close()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._tray.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()
            QApplication.quit()
