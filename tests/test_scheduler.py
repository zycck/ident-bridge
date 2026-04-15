# -*- coding: utf-8 -*-
"""Tests for app.core.scheduler.SyncScheduler."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import QObject

from app.core.scheduler import SyncScheduler


@pytest.fixture
def parent(qapp_session) -> QObject:
    """A QObject parent for the scheduler under test."""
    return QObject()


@pytest.fixture
def scheduler(parent) -> SyncScheduler:
    return SyncScheduler(parent)


# ── Configure / lifecycle ─────────────────────────────────────────────

def test_configure_sets_mode_and_value(scheduler):
    """configure() accepts valid modes without raising."""
    scheduler.configure("daily", "14:30")
    scheduler.configure("hourly", "1")


def test_configure_invalid_mode_raises_value_error(scheduler):
    """Unknown mode raises ValueError when start() is called."""
    scheduler.configure("garbage", "14:30")
    with pytest.raises(ValueError):
        scheduler.start()


def test_configure_cron_mode_raises_not_implemented(scheduler):
    """Cron mode raises NotImplementedError when start() is called."""
    scheduler.configure("cron", "* * * * *")
    with pytest.raises(NotImplementedError):
        scheduler.start()


def test_stop_clears_next_run(scheduler, qtbot):
    """stop() sets next_run to None and emits next_run_changed(None)."""
    scheduler.configure("hourly", "1")
    scheduler.start()
    assert scheduler.next_run() is not None

    with qtbot.wait_signal(scheduler.next_run_changed, timeout=1000) as blocker:
        scheduler.stop()

    assert scheduler.next_run() is None
    assert blocker.args[0] is None


def test_start_emits_next_run_changed(scheduler, qtbot):
    """start() emits next_run_changed with a datetime value.

    Note: start() internally calls stop() first, which emits next_run_changed(None).
    Then _schedule_next() emits next_run_changed(datetime). We collect all emissions
    and verify at least one carries a datetime payload.
    """
    scheduler.configure("daily", "14:30")
    emitted_values: list = []

    def _collect(value):
        emitted_values.append(value)

    scheduler.next_run_changed.connect(_collect)
    # wait_signals catches both emissions (None from stop(), datetime from _schedule_next)
    with qtbot.waitSignals(
        [scheduler.next_run_changed, scheduler.next_run_changed],
        timeout=1000,
    ):
        scheduler.start()
    scheduler.stop()

    # There should be at least one datetime in the emitted values
    datetime_values = [v for v in emitted_values if isinstance(v, datetime)]
    assert datetime_values, (
        f"Expected at least one datetime emission, got: {emitted_values}"
    )


# ── Daily mode ─────────────────────────────────────────────────────────

def test_daily_mode_next_run_today_if_in_future(scheduler):
    """A daily HH:MM that is later today → next_run is today at HH:MM."""
    now = datetime.now().astimezone()
    future = (now + timedelta(hours=1)).strftime("%H:%M")
    scheduler.configure("daily", future)
    scheduler.start()
    nr = scheduler.next_run()
    scheduler.stop()

    assert nr is not None
    assert nr.date() == now.date()


def test_daily_mode_next_run_tomorrow_if_past(scheduler):
    """A daily HH:MM that already passed today → next_run is tomorrow."""
    now = datetime.now().astimezone()
    past = (now - timedelta(hours=1)).strftime("%H:%M")
    scheduler.configure("daily", past)
    scheduler.start()
    nr = scheduler.next_run()
    scheduler.stop()

    assert nr is not None
    assert nr.date() == (now + timedelta(days=1)).date()


def test_daily_mode_invalid_format_raises(scheduler):
    """A daily value like 'abc' causes an exception (ValueError or similar)."""
    scheduler.configure("daily", "abc")
    # int("abc") raises ValueError inside _schedule_next
    with pytest.raises((ValueError, IndexError)):
        scheduler.start()


# ── Hourly mode ────────────────────────────────────────────────────────

def test_hourly_mode_next_run_in_future(scheduler):
    """Hourly 1 → next run is approximately 1 hour from now (±5% jitter)."""
    now = datetime.now().astimezone()
    scheduler.configure("hourly", "1")
    scheduler.start()
    nr = scheduler.next_run()
    scheduler.stop()

    assert nr is not None
    delta = nr - now
    # 3600s ± 5% = 3420s … 3780s → minutes 57 … 63
    assert timedelta(seconds=3420) <= delta <= timedelta(seconds=3780), (
        f"Unexpected delta: {delta}"
    )


def test_hourly_mode_4_hours(scheduler):
    """Hourly 4 → next run is approximately 4 hours from now (±5% jitter)."""
    now = datetime.now().astimezone()
    scheduler.configure("hourly", "4")
    scheduler.start()
    nr = scheduler.next_run()
    scheduler.stop()

    assert nr is not None
    delta = nr - now
    base = 4 * 3600  # 14400s
    margin = base * 0.05  # 720s
    assert timedelta(seconds=base - margin) <= delta <= timedelta(seconds=base + margin), (
        f"Unexpected delta: {delta}"
    )


# ── Signal firing ──────────────────────────────────────────────────────

def test_trigger_signal_can_be_emitted(scheduler, qtbot):
    """trigger signal exists and can be listened to."""
    scheduler.configure("hourly", "1")
    scheduler.start()
    with qtbot.wait_signal(scheduler.trigger, timeout=1000):
        scheduler.trigger.emit()
    scheduler.stop()


def test_next_run_changed_signal_exists(scheduler, qtbot):
    """next_run_changed is emitted on stop() even without prior start()."""
    # stop() always emits next_run_changed(None) regardless of state
    with qtbot.wait_signal(scheduler.next_run_changed, timeout=1000) as blocker:
        scheduler.stop()
    assert blocker.args[0] is None


# ── Jitter ─────────────────────────────────────────────────────────────

def test_jitter_within_5_percent(qapp_session):
    """Multiple starts produce next_run within ±5% of the base interval.

    Each SyncScheduler is created with qapp_session as parent so Qt keeps
    it alive (avoids premature QTimer GC when the local variable goes out of scope).
    """
    deltas = []
    schedulers = []  # keep references alive for the duration of the loop
    for _ in range(10):
        sch = SyncScheduler(qapp_session)
        schedulers.append(sch)
        sch.configure("hourly", "1")
        sch.start()
        nr = sch.next_run()
        if nr is not None:
            now = datetime.now().astimezone()
            deltas.append((nr - now).total_seconds())
        sch.stop()

    for sch in schedulers:
        sch.setParent(None)  # detach from qapp_session after the loop

    assert deltas, "No next_run values were collected"
    base = 3600.0
    margin = base * 0.05  # 180s
    for d in deltas:
        assert base - margin - 1 <= d <= base + margin + 1, (
            f"Jitter out of bounds: {d:.1f}s (expected {base - margin:.0f}..{base + margin:.0f})"
        )


# ── Stop is idempotent ────────────────────────────────────────────────

def test_stop_without_start_is_noop(scheduler):
    """stop() before start() should not crash and next_run() returns None."""
    scheduler.stop()
    assert scheduler.next_run() is None


def test_stop_is_idempotent(scheduler):
    """Calling stop() twice should not crash."""
    scheduler.configure("hourly", "1")
    scheduler.start()
    scheduler.stop()
    scheduler.stop()
    assert scheduler.next_run() is None


def test_double_start_replaces_previous(scheduler):
    """Calling start() twice replaces the previous timer; both times next_run is set."""
    scheduler.configure("hourly", "1")
    scheduler.start()
    first = scheduler.next_run()
    scheduler.start()
    second = scheduler.next_run()
    scheduler.stop()

    assert first is not None
    assert second is not None
    # Both should be within plausible range (~1 hour from now)
    now = datetime.now().astimezone()
    for nr in (first, second):
        delta = nr - now
        assert timedelta(seconds=3400) <= delta <= timedelta(seconds=3800)


# ── DST-awareness sanity ──────────────────────────────────────────────

def test_next_run_is_timezone_aware(scheduler):
    """next_run() should be timezone-aware (not a naive datetime)."""
    scheduler.configure("daily", "12:00")
    scheduler.start()
    nr = scheduler.next_run()
    scheduler.stop()

    assert nr is not None
    assert nr.tzinfo is not None, "next_run is naive — DST-aware fix lost"


def test_hourly_next_run_is_timezone_aware(scheduler):
    """next_run() for hourly mode should also be timezone-aware."""
    scheduler.configure("hourly", "2")
    scheduler.start()
    nr = scheduler.next_run()
    scheduler.stop()

    assert nr is not None
    assert nr.tzinfo is not None, "hourly next_run is naive"


# ── Minutely mode ─────────────────────────────────────────────────────

def test_minutely_mode_5_minutes(parent):
    sch = SyncScheduler(parent)
    sch.configure("minutely", "5")
    sch.start()
    nr = sch.next_run()
    assert nr is not None
    now = datetime.now().astimezone()
    delta = nr - now
    # 5 minutes = 300s ± 5% jitter (±15s) → allow 280..320
    assert timedelta(seconds=280) <= delta <= timedelta(seconds=320), (
        f"Unexpected delta: {delta}"
    )
    sch.stop()


def test_minutely_mode_1_minute(parent):
    sch = SyncScheduler(parent)
    sch.configure("minutely", "1")
    sch.start()
    nr = sch.next_run()
    assert nr is not None
    now = datetime.now().astimezone()
    delta = nr - now
    # 1 minute = 60s ± 5% jitter (±3s) → allow 55..65
    assert timedelta(seconds=55) <= delta <= timedelta(seconds=65), (
        f"Unexpected delta: {delta}"
    )
    sch.stop()


def test_minutely_invalid_value(parent):
    """minutely with value 0 should not crash — _schedule_next returns early."""
    sch = SyncScheduler(parent)
    sch.configure("minutely", "0")
    sch.start()  # must not raise
    # next_run stays None because _schedule_next returned early
    assert sch.next_run() is None
    sch.stop()


# ── Secondly mode ─────────────────────────────────────────────────────

def test_secondly_mode_30_seconds(parent):
    sch = SyncScheduler(parent)
    sch.configure("secondly", "30")
    sch.start()
    nr = sch.next_run()
    assert nr is not None
    now = datetime.now().astimezone()
    delta = nr - now
    # 30 seconds ± 5% jitter (±1.5s) → allow 28..32
    assert timedelta(seconds=28) <= delta <= timedelta(seconds=32), (
        f"Unexpected delta: {delta}"
    )
    sch.stop()


def test_secondly_mode_10_seconds(parent):
    sch = SyncScheduler(parent)
    sch.configure("secondly", "10")
    sch.start()
    nr = sch.next_run()
    assert nr is not None
    now = datetime.now().astimezone()
    delta = nr - now
    # 10 seconds ± 5% jitter (±0.5s) → allow 9..12
    assert timedelta(seconds=9) <= delta <= timedelta(seconds=12), (
        f"Unexpected delta: {delta}"
    )
    sch.stop()


def test_secondly_real_trigger_fires(parent, qtbot):
    """Live test: configure 1-second secondly, wait for trigger signal."""
    sch = SyncScheduler(parent)
    sch.configure("secondly", "1")
    sch.start()
    with qtbot.wait_signal(sch.trigger, timeout=5000):
        pass  # should fire within ~1s (max 1s + 5% jitter)
    sch.stop()
