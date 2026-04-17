"""Signal wiring helper for MainWindow cross-widget routing."""

from PySide6.QtWidgets import QSystemTrayIcon

from app.config import SyncResult


class MainWindowSignalRouter:
    def __init__(self, *, dashboard, export_jobs, update_flow, tray) -> None:
        self._dashboard = dashboard
        self._export_jobs = export_jobs
        self._update_flow = update_flow
        self._tray = tray

    def wire(self) -> None:
        self._dashboard.update_requested.connect(
            self._update_flow.on_update_requested
        )
        self._export_jobs.sync_completed.connect(self._on_sync_completed)
        self._export_jobs.history_changed.connect(self._dashboard.refresh_activity)
        self._export_jobs.failure_alert.connect(self._on_export_failure_alert)

    def _on_sync_completed(self, result: SyncResult) -> None:
        self._dashboard.update_last_sync(result)

    def _on_export_failure_alert(self, job_name: str, count: int) -> None:
        self._tray.showMessage(
            "iDentBridge — ошибка выгрузки",
            f"«{job_name}» — {count} неудачных запусков подряд. "
            f"Откройте приложение, чтобы посмотреть детали.",
            QSystemTrayIcon.MessageIcon.Warning,
            8000,
        )
