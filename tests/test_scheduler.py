"""Tests for app.core.scheduler.SyncScheduler."""

from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QObject

from app.core.scheduler import ScheduleMode, SyncScheduler, schedule_value_is_valid


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current

    def set(self, current: datetime) -> None:
        self.current = current


def _base_now() -> datetime:
    return datetime.now().astimezone().replace(
        year=2026,
        month=4,
        day=22,
        hour=10,
        minute=0,
        second=0,
        microsecond=0,
    )


@pytest.fixture
def parent(qapp_session) -> QObject:
    return QObject()


@pytest.fixture
def scheduler(parent) -> SyncScheduler:
    return SyncScheduler(parent)


def make_scheduler(parent: QObject, current: datetime) -> tuple[SyncScheduler, FakeClock]:
    clock = FakeClock(current)
    return SyncScheduler(parent, now_func=clock), clock


def test_configure_sets_mode_and_value(scheduler) -> None:
    scheduler.configure("daily", "14:30")
    scheduler.configure("hourly", "1")
    scheduler.configure("minutely", "5")
    scheduler.configure("secondly", "10")


def test_schedule_mode_is_str_enum() -> None:
    assert issubclass(ScheduleMode, str)
    assert ScheduleMode("daily") is ScheduleMode.DAILY


@pytest.mark.parametrize("mode,value", [("garbage", "14:30"), ("cron", "* * * * *")])
def test_configure_invalid_mode_raises_value_error(scheduler, mode, value) -> None:
    with pytest.raises(ValueError):
        scheduler.configure(mode, value)


@pytest.mark.parametrize(
    ("mode", "value"),
    [
        ("daily", "08:30"),
        ("hourly", "2"),
        ("minutely", "15"),
        ("secondly", "10"),
    ],
)
def test_schedule_value_validation_accepts_supported_values(mode, value) -> None:
    assert schedule_value_is_valid(mode, value) is True


@pytest.mark.parametrize(
    ("mode", "value"),
    [
        ("daily", "bad"),
        ("daily", "24:00"),
        ("hourly", "0"),
        ("minutely", "0"),
        ("secondly", "0"),
        ("unknown", "1"),
    ],
)
def test_schedule_value_validation_rejects_invalid_values(mode, value) -> None:
    assert schedule_value_is_valid(mode, value) is False


@pytest.mark.parametrize(
    ("mode", "value"),
    [("daily", "bad"), ("hourly", "0"), ("minutely", "0"), ("secondly", "0")],
)
def test_configure_invalid_value_raises_value_error(scheduler, mode, value) -> None:
    with pytest.raises(ValueError):
        scheduler.configure(mode, value)


def test_stop_clears_next_run(scheduler, qtbot) -> None:
    scheduler.configure("hourly", "1")
    scheduler.start()
    assert scheduler.next_run() is not None

    with qtbot.wait_signal(scheduler.next_run_changed, timeout=1000) as blocker:
        scheduler.stop()

    assert scheduler.next_run() is None
    assert blocker.args[0] is None


def test_start_emits_next_run_changed(scheduler, qtbot) -> None:
    scheduler.configure("daily", "14:30")
    emitted_values: list[object] = []

    scheduler.next_run_changed.connect(emitted_values.append)
    with qtbot.waitSignals(
        [scheduler.next_run_changed, scheduler.next_run_changed],
        timeout=1000,
    ):
        scheduler.start()
    scheduler.stop()

    assert any(isinstance(value, datetime) for value in emitted_values)


def test_daily_mode_next_run_today_if_in_future(parent) -> None:
    now = _base_now().replace(hour=10, minute=15)
    scheduler, _clock = make_scheduler(parent, now)
    scheduler.configure("daily", "14:30")
    scheduler.start()
    assert scheduler.next_run() == now.replace(hour=14, minute=30, second=0, microsecond=0)
    scheduler.stop()


def test_daily_mode_next_run_tomorrow_if_past(parent) -> None:
    now = _base_now().replace(hour=18, minute=45)
    scheduler, _clock = make_scheduler(parent, now)
    scheduler.configure("daily", "08:30")
    scheduler.start()
    assert scheduler.next_run() == now.replace(
        day=23,
        hour=8,
        minute=30,
        second=0,
        microsecond=0,
    )
    scheduler.stop()


def test_daily_mode_keeps_wall_clock_anchor_when_fire_is_late(parent) -> None:
    now = _base_now().replace(hour=8, minute=0)
    scheduler, clock = make_scheduler(parent, now)
    scheduler.configure("daily", "09:30")
    scheduler.start()
    assert scheduler.next_run() == now.replace(hour=9, minute=30)

    clock.set(now.replace(hour=9, minute=35))
    scheduler._fire()

    assert scheduler.next_run() == now.replace(day=23, hour=9, minute=30)
    scheduler.stop()


def test_daily_mode_invalid_format_raises(scheduler) -> None:
    with pytest.raises(ValueError):
        scheduler.configure("daily", "abc")


def test_hourly_mode_next_run_is_exact_interval(parent) -> None:
    now = _base_now().replace(hour=10, minute=15)
    scheduler, _clock = make_scheduler(parent, now)
    scheduler.configure("hourly", "1")
    scheduler.start()
    assert scheduler.next_run() == now + timedelta(hours=1)
    scheduler.stop()


def test_hourly_mode_4_hours_is_exact_interval(parent) -> None:
    now = _base_now().replace(hour=10, minute=15)
    scheduler, _clock = make_scheduler(parent, now)
    scheduler.configure("hourly", "4")
    scheduler.start()
    assert scheduler.next_run() == now + timedelta(hours=4)
    scheduler.stop()


def test_hourly_mode_fire_does_not_drift_from_delayed_handler(parent) -> None:
    now = _base_now().replace(hour=10, minute=0)
    scheduler, clock = make_scheduler(parent, now)
    scheduler.configure("hourly", "1")
    scheduler.start()
    assert scheduler.next_run() == now + timedelta(hours=1)

    clock.set(now.replace(hour=11, minute=7))
    scheduler._fire()

    assert scheduler.next_run() == now.replace(hour=12, minute=0)
    scheduler.stop()


def test_hourly_mode_fire_catches_up_when_multiple_slots_are_missed(parent) -> None:
    now = _base_now().replace(hour=10, minute=0)
    scheduler, clock = make_scheduler(parent, now)
    scheduler.configure("hourly", "1")
    scheduler.start()
    assert scheduler.next_run() == now + timedelta(hours=1)

    clock.set(now.replace(hour=13, minute=5))
    scheduler._fire()

    assert scheduler.next_run() == now.replace(hour=14, minute=0)
    scheduler.stop()


def test_minutely_mode_5_minutes_is_exact_interval(parent) -> None:
    now = _base_now().replace(hour=10, minute=15, second=12)
    scheduler, _clock = make_scheduler(parent, now)
    scheduler.configure("minutely", "5")
    scheduler.start()
    assert scheduler.next_run() == now + timedelta(minutes=5)
    scheduler.stop()


def test_secondly_mode_30_seconds_is_exact_interval(parent) -> None:
    now = _base_now().replace(hour=10, minute=15, second=12)
    scheduler, _clock = make_scheduler(parent, now)
    scheduler.configure("secondly", "30")
    scheduler.start()
    assert scheduler.next_run() == now + timedelta(seconds=30)
    scheduler.stop()


def test_trigger_signal_can_be_emitted(scheduler, qtbot) -> None:
    scheduler.configure("hourly", "1")
    scheduler.start()
    with qtbot.wait_signal(scheduler.trigger, timeout=1000):
        scheduler.trigger.emit()
    scheduler.stop()


def test_next_run_changed_signal_exists(scheduler, qtbot) -> None:
    with qtbot.wait_signal(scheduler.next_run_changed, timeout=1000) as blocker:
        scheduler.stop()
    assert blocker.args[0] is None


def test_stop_without_start_is_noop(scheduler) -> None:
    scheduler.stop()
    assert scheduler.next_run() is None


def test_stop_is_idempotent(scheduler) -> None:
    scheduler.configure("hourly", "1")
    scheduler.start()
    scheduler.stop()
    scheduler.stop()
    assert scheduler.next_run() is None


def test_double_start_replaces_previous_anchor(parent) -> None:
    now = _base_now().replace(hour=10, minute=0)
    scheduler, clock = make_scheduler(parent, now)
    scheduler.configure("hourly", "1")
    scheduler.start()
    assert scheduler.next_run() == now + timedelta(hours=1)

    clock.set(now.replace(hour=10, minute=20))
    scheduler.start()

    assert scheduler.next_run() == now.replace(hour=11, minute=20)
    scheduler.stop()


def test_next_run_is_timezone_aware_for_daily(parent) -> None:
    scheduler, _clock = make_scheduler(parent, _base_now())
    scheduler.configure("daily", "12:00")
    scheduler.start()
    next_run = scheduler.next_run()
    scheduler.stop()

    assert next_run is not None
    assert next_run.tzinfo is not None


def test_hourly_next_run_is_timezone_aware(parent) -> None:
    scheduler, _clock = make_scheduler(parent, _base_now())
    scheduler.configure("hourly", "2")
    scheduler.start()
    next_run = scheduler.next_run()
    scheduler.stop()

    assert next_run is not None
    assert next_run.tzinfo is not None


def test_secondly_real_trigger_fires(parent, qtbot) -> None:
    scheduler = SyncScheduler(parent)
    scheduler.configure("secondly", "1")
    scheduler.start()
    with qtbot.wait_signal(scheduler.trigger, timeout=5000):
        pass
    scheduler.stop()
