# -*- coding: utf-8 -*-
"""MainWindow — top-level application shell for iDentBridge."""
from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.ui.title_bar import CustomTitleBar

from app.config import ConfigManager
from app.core.app_logger import get_logger
from app.core.constants import NAV_SIDEBAR_W
from app.core.updater import GITHUB_REPO, download_and_apply
from app.ui.dashboard_widget import DashboardWidget
from app.ui.debug_window import DebugWindow
from app.ui.error_dialog import install_global_handler
from app.ui.export_jobs_widget import ExportJobsWidget
from app.ui.lucide_icons import lucide
from app.ui.settings_widget import SettingsWidget
from app.ui.theme import Theme
from app.ui.threading import run_worker
from app.workers.update_worker import UpdateWorker

_log = get_logger(__name__)


_NAV_LABELS       = ("Статус", "Выгрузки", "Настройки")
_NAV_LUCIDE_ICONS = ("bar-chart-3", "upload-cloud", "settings")


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

        # Strong ref to update worker — GC kills workers without explicit Python reference
        self._update_worker: object | None = None

        # Debug window — created lazily on first Ctrl+D press
        self._debug_window: DebugWindow | None = None

        self._build_ui()
        self._build_tray()
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

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(NAV_SIDEBAR_W)
        nav_layout = QVBoxLayout(sidebar)
        nav_layout.setContentsMargins(8, 16, 8, 16)
        nav_layout.setSpacing(4)

        self._nav_btns: list[QPushButton] = []
        self._nav_icons_normal: list[QIcon] = []
        self._nav_icons_active: list[QIcon] = []

        for i, (label, name) in enumerate(zip(_NAV_LABELS, _NAV_LUCIDE_ICONS)):
            icon_n = lucide(name, color=Theme.gray_500)
            icon_a = lucide(name, color=Theme.primary_500)
            self._nav_icons_normal.append(icon_n)
            self._nav_icons_active.append(icon_a)
            btn = QPushButton(f"  {label}")
            btn.setObjectName("navBtn")
            btn.setIcon(icon_n)
            btn.clicked.connect(lambda checked=False, idx=i: self.navigate(idx))
            nav_layout.addWidget(btn)
            self._nav_btns.append(btn)
        nav_layout.addStretch()

        debug_btn = QPushButton("  Debug")
        debug_btn.setObjectName("navBtn")
        debug_btn.setIcon(lucide('bug', color=Theme.gray_500))
        debug_btn.setToolTip("Панель отладки (Ctrl+D)")
        debug_btn.clicked.connect(self._toggle_debug_window)
        nav_layout.addWidget(debug_btn)

        # ── Footer: version + developer Telegram link (single line) ──────
        footer_lbl = QLabel(
            f'<span style="color: {Theme.gray_400};">v{self._current_version}</span>'
            f'  ·  '
            f'<a href="https://t.me/zycck" '
            f'style="color: {Theme.primary_700}; text-decoration: none;">@zycck</a>'
        )
        footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_lbl.setOpenExternalLinks(True)
        footer_lbl.setStyleSheet(
            f"font-size: {Theme.font_size_xs}pt; "
            f"background: transparent; "
            f"padding: 8px 4px;"
        )
        footer_lbl.setToolTip("Связаться с разработчиком в Telegram")
        nav_layout.addWidget(footer_lbl)

        # Stacked pages
        self._stack = QStackedWidget()
        self._dashboard = DashboardWidget(self._config, self)
        self._export_jobs = ExportJobsWidget(self._config, self)
        self._settings_widget = SettingsWidget(
            self._config, self._current_version, self
        )
        self._stack.addWidget(self._dashboard)        # index 0
        self._stack.addWidget(self._export_jobs)      # index 1
        self._stack.addWidget(self._settings_widget)  # index 2

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
        app_icon = QApplication.instance().windowIcon()  # type: ignore[union-attr]
        if app_icon.isNull():
            # Fallback — shouldn't happen if main._load_app_icon ran first
            app_icon = QIcon()
        self._tray = QSystemTrayIcon(app_icon, self)
        self._tray.setToolTip("iDentBridge")

        menu = QMenu()
        menu.addAction("Открыть", self._show_window)
        menu.addSeparator()
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
            active = (i == index)
            btn.setObjectName("navBtnActive" if active else "navBtn")
            btn.setIcon(self._nav_icons_active[i] if active else self._nav_icons_normal[i])
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ------------------------------------------------------------------
    # Update flow
    # ------------------------------------------------------------------

    def _run_update_check_silently(self) -> None:
        worker = UpdateWorker(current_version=self._current_version, repo=GITHUB_REPO)
        thread = run_worker(self, worker, pin_attr="_update_worker", entry="check")
        worker.update_available.connect(self._on_update_available)
        worker.update_available.connect(thread.quit)
        worker.no_update.connect(thread.quit)
        worker.error.connect(thread.quit)

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

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self._show_window()

    def _quit(self) -> None:
        QApplication.quit()

    @Slot()
    def _cleanup(self) -> None:
        """Called by aboutToQuit — stop background services before exit."""
        _log.info("Shutting down…")
        self._export_jobs.stop_all_schedulers()
        self._dashboard.stop()
        if self._debug_window is not None:
            self._debug_window.close()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._tray.isVisible():
            cfg = self._config.load()
            if not cfg.get("tray_notice_shown"):
                self._tray.showMessage(
                    "iDentBridge свёрнут в трей",
                    "Приложение продолжает работать в фоне. "
                    "Кликните по иконке в системном трее, чтобы вернуться.",
                    QSystemTrayIcon.MessageIcon.Information,
                    6000,
                )
                self._config.update(tray_notice_shown=True)
            self.hide()
            event.ignore()
        else:
            event.accept()
            QApplication.quit()
