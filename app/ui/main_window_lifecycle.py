# -*- coding: utf-8 -*-
"""Tray/shutdown lifecycle helpers extracted from MainWindow."""

from collections.abc import Callable
import os

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QIcon
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from app.config import ConfigManager
from app.core.app_logger import get_logger

_log = get_logger(__name__)


def _force_quit_on_close() -> bool:
    return os.environ.get("IDENTBRIDGE_FORCE_QUIT_ON_CLOSE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_tray(
    parent: QMainWindow,
    *,
    on_open: Callable[[], None],
    on_check_update: Callable[[], None],
    on_quit: Callable[[], None],
    on_activated: Callable[[QSystemTrayIcon.ActivationReason], None],
) -> QSystemTrayIcon:
    app_icon = QApplication.instance().windowIcon()  # type: ignore[union-attr]
    if app_icon.isNull():
        app_icon = QIcon()

    tray = QSystemTrayIcon(app_icon, parent)
    tray.setToolTip("iDentBridge")

    menu = QMenu()
    menu.addAction("Открыть", on_open)
    menu.addSeparator()
    menu.addAction("Проверить обновление", on_check_update)
    menu.addSeparator()
    menu.addAction("Выход", on_quit)

    tray.setContextMenu(menu)
    tray.activated.connect(on_activated)
    tray.show()
    return tray


class MainWindowLifecycleController(QObject):
    """Owns tray visibility, close-to-tray, and shutdown cleanup behavior."""

    def __init__(
        self,
        *,
        window: QMainWindow,
        config: ConfigManager,
        tray: QSystemTrayIcon,
        export_jobs: object,
        dashboard: object,
        close_debug_window: Callable[[], None],
        quit_app: Callable[[], None] = QApplication.quit,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._config = config
        self._tray = tray
        self._export_jobs = export_jobs
        self._dashboard = dashboard
        self._close_debug_window = close_debug_window
        self._quit_app = quit_app

    def show_tray_message(self, title: str, message: str) -> None:
        self._tray.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )

    def show_window(self) -> None:
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    @Slot(QSystemTrayIcon.ActivationReason)
    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            self.show_window()

    def quit(self) -> None:
        self._quit_app()

    @Slot()
    def cleanup(self) -> None:
        _log.info("Shutting down…")
        self._export_jobs.stop_all_schedulers()
        self._dashboard.stop()
        self._close_debug_window()

    def handle_close_event(self, event: QCloseEvent) -> None:
        if _force_quit_on_close():
            event.accept()
            self._quit_app()
            return
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
            self._window.hide()
            event.ignore()
            return

        event.accept()
        self._quit_app()
