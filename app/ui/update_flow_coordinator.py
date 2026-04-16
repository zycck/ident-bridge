# -*- coding: utf-8 -*-
"""Update-flow orchestration extracted from MainWindow."""
from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox

from app.core.app_logger import get_logger
from app.core.updater import GITHUB_REPO, apply_downloaded_update
from app.ui.dashboard_widget import DashboardWidget
from app.ui.threading import run_worker
from app.workers.update_worker import UpdateDownloadWorker, UpdateWorker

_log = get_logger(__name__)


class UpdateFlowCoordinator(QObject):
    """Keep update-check/download flow out of MainWindow without changing UX."""

    def __init__(
        self,
        window: QMainWindow,
        dashboard: DashboardWidget,
        *,
        current_version: str,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._dashboard = dashboard
        self._current_version = current_version
        self._update_worker: object | None = None
        self._update_download_worker: object | None = None
        self._update_download_running = False

    def run_silent_check(self) -> None:
        worker = UpdateWorker(current_version=self._current_version, repo=GITHUB_REPO)
        thread = run_worker(self, worker, pin_attr="_update_worker", entry="check")
        worker.update_available.connect(self.on_update_available)
        worker.update_available.connect(thread.quit)
        worker.no_update.connect(thread.quit)
        worker.error.connect(thread.quit)

    @Slot(str, str)
    def on_update_available(self, version: str, url: str) -> None:
        self._window.show_tray_message(
            "Доступно обновление",
            f"Версия {version} готова к установке.",
        )
        self._dashboard.show_update_banner(version, url)

    @Slot(str)
    def on_update_requested(self, url: str) -> None:
        if self._update_download_running:
            return

        self._update_download_running = True
        self._dashboard.set_update_in_progress(True)

        worker = UpdateDownloadWorker(url)
        run_worker(
            self,
            worker,
            pin_attr="_update_download_worker",
            on_finished=self.on_update_download_finished,
            on_error=self.on_update_download_error,
        )
        worker.downloaded.connect(self.on_update_downloaded)

    @Slot(str)
    def on_update_downloaded(self, downloaded_path: str) -> None:
        try:
            apply_downloaded_update(downloaded_path, exit_hook=QApplication.quit)
        except Exception as exc:  # noqa: BLE001
            self._update_download_running = False
            self._dashboard.set_update_in_progress(False)
            QMessageBox.warning(self._window, "Ошибка обновления", str(exc))

    @Slot()
    def on_update_download_finished(self) -> None:
        # Successful update application exits the app; reaching here means we
        # should restore the UI for non-fatal paths only.
        if self._update_download_running:
            self._update_download_running = False
            self._dashboard.set_update_in_progress(False)

    @Slot(str)
    def on_update_download_error(self, message: str) -> None:
        self._update_download_running = False
        self._dashboard.set_update_in_progress(False)
        QMessageBox.warning(self._window, "Ошибка обновления", message)
