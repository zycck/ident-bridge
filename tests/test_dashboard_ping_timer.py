"""Tests for extracted dashboard ping timer controller."""

from PySide6.QtCore import QObject

from app.ui.dashboard_ping_timer import DashboardPingTimerController


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks: list = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeTimer:
    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.interval = None
        self.started = 0
        self.stopped = 0
        self.timeout = _FakeSignal()

    def setInterval(self, interval: int) -> None:
        self.interval = interval

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


def test_ping_timer_start_configures_timer_and_schedules_first_ping() -> None:
    pings: list[str] = []
    single_shots: list[tuple[int, object]] = []

    controller = DashboardPingTimerController(
        parent=QObject(),
        ping=lambda: pings.append("ping"),
        interval_ms=1234,
        timer_factory=_FakeTimer,
        single_shot=lambda delay, callback: single_shots.append((delay, callback)),
    )

    controller.start()

    assert controller._timer is not None
    assert controller._timer.interval == 1234
    assert controller._timer.started == 1
    assert len(controller._timer.timeout.callbacks) == 1
    assert single_shots and single_shots[0][0] == 1500

    controller._timer.timeout.callbacks[0]()
    single_shots[0][1]()
    assert pings == ["ping", "ping"]


def test_ping_timer_stop_is_safe_before_and_after_start() -> None:
    controller = DashboardPingTimerController(
        parent=QObject(),
        ping=lambda: None,
        interval_ms=1234,
        timer_factory=_FakeTimer,
        single_shot=lambda delay, callback: None,
    )

    controller.stop()
    controller.start()
    controller.stop()

    assert controller._timer is not None
    assert controller._timer.stopped == 1
