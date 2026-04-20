"""Tests for the extracted update flow coordinator."""

from PySide6.QtWidgets import QMainWindow

from app.ui.update_flow_coordinator import UpdateFlowCoordinator
from app.workers.update_worker import UpdateDownloadWorker


class _FakeDashboard:
    def __init__(self) -> None:
        self.banner_calls: list[tuple[str, str]] = []
        self.in_progress: list[bool] = []

    def show_update_banner(self, version: str, url: str) -> None:
        self.banner_calls.append((version, url))

    def set_update_in_progress(self, running: bool) -> None:
        self.in_progress.append(running)


class _FakeWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.tray_messages: list[tuple[str, str]] = []

    def show_tray_message(self, title: str, message: str) -> None:
        self.tray_messages.append((title, message))


def test_update_flow_coordinator_passes_digest_to_download_worker(
    monkeypatch,
    qapp_session,
) -> None:
    digest = "a" * 64
    window = _FakeWindow()
    dashboard = _FakeDashboard()
    captured: dict[str, object] = {}

    def fake_run_worker(parent, worker, **kwargs):
        captured["worker"] = worker
        captured["kwargs"] = kwargs
        return None

    monkeypatch.setattr("app.ui.update_flow_coordinator.run_worker", fake_run_worker)

    coordinator = UpdateFlowCoordinator(
        window,
        dashboard,
        current_version="1.0.0",
    )

    coordinator.on_update_available(
        "v1.2.3",
        "https://example.com/update.exe",
        f"sha256:{digest}",
    )
    coordinator.on_update_requested("https://example.com/update.exe")

    assert window.tray_messages == [("Доступно обновление", "Версия v1.2.3 готова к установке.")]
    assert dashboard.banner_calls == [("v1.2.3", "https://example.com/update.exe")]
    assert dashboard.in_progress == [True]
    assert isinstance(captured["worker"], UpdateDownloadWorker)
    assert captured["worker"]._expected_digest == f"sha256:{digest}"
