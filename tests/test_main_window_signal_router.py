# -*- coding: utf-8 -*-
"""Tests for extracted MainWindow signal routing helpers."""

from datetime import datetime

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QSystemTrayIcon

from app.config import SyncResult
from app.ui.main_window_signal_router import MainWindowSignalRouter


class _FakeDashboard(QObject):
    update_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.last_sync_results: list[SyncResult] = []
        self.refresh_calls = 0

    def update_last_sync(self, result: SyncResult) -> None:
        self.last_sync_results.append(result)

    def refresh_activity(self) -> None:
        self.refresh_calls += 1


class _FakeExportJobs(QObject):
    sync_completed = Signal(object)
    history_changed = Signal()
    failure_alert = Signal(str, int)


class _FakeUpdateFlow:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    def on_update_requested(self, url: str) -> None:
        self.requested_urls.append(url)


class _FakeTray:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, object, int]] = []

    def showMessage(self, title: str, message: str, icon, timeout: int) -> None:
        self.messages.append((title, message, icon, timeout))


def _result() -> SyncResult:
    return SyncResult(
        success=True,
        rows_synced=5,
        error=None,
        timestamp=datetime(2026, 4, 16, 11, 22, 33),
    )


def test_signal_router_wires_dashboard_update_requests() -> None:
    dashboard = _FakeDashboard()
    export_jobs = _FakeExportJobs()
    update_flow = _FakeUpdateFlow()
    tray = _FakeTray()

    router = MainWindowSignalRouter(
        dashboard=dashboard,
        export_jobs=export_jobs,
        update_flow=update_flow,
        tray=tray,
    )
    router.wire()

    dashboard.update_requested.emit("https://example.com/app.exe")

    assert update_flow.requested_urls == ["https://example.com/app.exe"]


def test_signal_router_wires_export_results_to_dashboard() -> None:
    dashboard = _FakeDashboard()
    export_jobs = _FakeExportJobs()
    update_flow = _FakeUpdateFlow()
    tray = _FakeTray()
    result = _result()

    router = MainWindowSignalRouter(
        dashboard=dashboard,
        export_jobs=export_jobs,
        update_flow=update_flow,
        tray=tray,
    )
    router.wire()

    export_jobs.sync_completed.emit(result)
    export_jobs.history_changed.emit()

    assert dashboard.last_sync_results == [result]
    assert dashboard.refresh_calls == 1


def test_signal_router_routes_export_failure_alerts_to_tray() -> None:
    dashboard = _FakeDashboard()
    export_jobs = _FakeExportJobs()
    update_flow = _FakeUpdateFlow()
    tray = _FakeTray()

    router = MainWindowSignalRouter(
        dashboard=dashboard,
        export_jobs=export_jobs,
        update_flow=update_flow,
        tray=tray,
    )
    router.wire()

    export_jobs.failure_alert.emit("Orders", 3)

    assert tray.messages == [
        (
            "iDentBridge — ошибка выгрузки",
            "«Orders» — 3 неудачных запусков подряд. Откройте приложение, чтобы посмотреть детали.",
            QSystemTrayIcon.MessageIcon.Warning,
            8000,
        )
    ]
