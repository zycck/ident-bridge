# -*- coding: utf-8 -*-
"""Tests for extracted MainWindow tray/shutdown lifecycle helpers."""

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow, QSystemTrayIcon

from app.ui.main_window_lifecycle import MainWindowLifecycleController


class _FakeTray:
    def __init__(self, *, visible: bool = True) -> None:
        self.visible = visible
        self.messages: list[tuple] = []

    def isVisible(self) -> bool:
        return self.visible

    def hide(self) -> None:
        self.visible = False

    def showMessage(self, title: str, message: str, icon, timeout: int) -> None:
        self.messages.append((title, message, icon, timeout))


class _FakeExportJobs:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop_all_schedulers(self) -> None:
        self.stop_calls += 1


class _FakeDashboard:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class _Window(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.raise_calls = 0
        self.activate_calls = 0

    def raise_(self) -> None:  # type: ignore[override]
        self.raise_calls += 1
        super().raise_()

    def activateWindow(self) -> None:  # type: ignore[override]
        self.activate_calls += 1
        super().activateWindow()


def _build_controller(qtbot, tmp_config, *, tray_visible: bool = True):
    window = _Window()
    qtbot.addWidget(window)
    tray = _FakeTray(visible=tray_visible)
    export_jobs = _FakeExportJobs()
    dashboard = _FakeDashboard()
    debug_closed: list[bool] = []
    quit_calls: list[bool] = []

    controller = MainWindowLifecycleController(
        window=window,
        config=tmp_config,
        tray=tray,
        export_jobs=export_jobs,
        dashboard=dashboard,
        close_debug_window=lambda: debug_closed.append(True),
        quit_app=lambda: quit_calls.append(True),
    )
    return controller, window, tray, export_jobs, dashboard, debug_closed, quit_calls


def test_cleanup_stops_services_and_closes_debug_window(qtbot, tmp_config) -> None:
    controller, _, _, export_jobs, dashboard, debug_closed, _ = _build_controller(
        qtbot,
        tmp_config,
    )

    controller.cleanup()

    assert export_jobs.stop_calls == 1
    assert dashboard.stop_calls == 1
    assert debug_closed == [True]


def test_handle_close_event_hides_window_and_sets_notice_once(qtbot, tmp_config) -> None:
    controller, window, tray, _, _, _, _ = _build_controller(
        qtbot,
        tmp_config,
        tray_visible=True,
    )
    window.show()

    first = QCloseEvent()
    controller.handle_close_event(first)
    cfg = tmp_config.load()

    assert first.isAccepted() is False
    assert window.isHidden() is True
    assert cfg["tray_notice_shown"] is True
    assert len(tray.messages) == 1

    second = QCloseEvent()
    controller.handle_close_event(second)

    assert second.isAccepted() is False
    assert len(tray.messages) == 1


def test_handle_close_event_accepts_and_quits_when_tray_hidden(qtbot, tmp_config) -> None:
    controller, _, _, _, _, _, quit_calls = _build_controller(
        qtbot,
        tmp_config,
        tray_visible=False,
    )
    event = QCloseEvent()

    controller.handle_close_event(event)

    assert event.isAccepted() is True
    assert quit_calls == [True]


def test_tray_activation_restores_window_on_click(qtbot, tmp_config) -> None:
    controller, window, _, _, _, _, _ = _build_controller(qtbot, tmp_config)

    controller.on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)

    assert window.raise_calls == 1
    assert window.activate_calls == 1
