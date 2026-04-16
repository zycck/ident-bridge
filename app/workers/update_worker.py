"""
UpdateWorker — checks GitHub for a newer release (moveToThread pattern).

Usage:
    thread = QThread()
    worker = UpdateWorker(current_version="1.2.3", repo="zycck/ident-bridge")
    worker.moveToThread(thread)
    thread.start()
    worker.check()   # call directly after thread starts, or connect to a signal
"""
from PySide6.QtCore import QObject, Signal, Slot

from app.core.updater import check_latest, download_update, is_newer


class UpdateWorker(QObject):
    """QObject worker that checks GitHub releases for a newer version."""

    # Emitted when a newer release exists: (tag, download_url)
    update_available: Signal = Signal(str, str)
    # Emitted when the current version is already up-to-date
    no_update: Signal = Signal()
    # Emitted on network / parse errors
    error: Signal = Signal(str)
    # Terminal signal — always emitted exactly once when check() completes
    finished: Signal = Signal()

    def __init__(self, current_version: str, repo: str) -> None:
        super().__init__()
        self._current_version = current_version
        self._repo = repo

    @Slot()
    def check(self) -> None:
        """Fetch the latest GitHub release and emit the appropriate signal."""
        try:
            try:
                release = check_latest(self._repo)
                if release is None:
                    self.error.emit("Не удалось получить информацию о релизе")
                    return
                tag, download_url = release
                if is_newer(tag, self._current_version):
                    self.update_available.emit(tag, download_url)
                else:
                    self.no_update.emit()
            except Exception as exc:  # noqa: BLE001
                self.error.emit(str(exc))
        finally:
            self.finished.emit()


class UpdateDownloadWorker(QObject):
    """Downloads the update payload off the GUI thread."""

    downloaded: Signal = Signal(str)
    error: Signal = Signal(str)
    finished: Signal = Signal()

    def __init__(self, download_url: str) -> None:
        super().__init__()
        self._download_url = download_url

    @Slot()
    def run(self) -> None:
        try:
            path = download_update(self._download_url)
            self.downloaded.emit(path)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))
        finally:
            self.finished.emit()
