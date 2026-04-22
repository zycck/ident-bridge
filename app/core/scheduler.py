import logging
import os
import re
from datetime import datetime, timedelta
from enum import StrEnum, UNIQUE, verify

from PySide6.QtCore import QObject, QTimer, Signal

_log = logging.getLogger(__name__)


@verify(UNIQUE)
class ScheduleMode(StrEnum):
    """Supported recurrence modes for export scheduling."""

    DAILY = "daily"
    HOURLY = "hourly"
    MINUTELY = "minutely"
    SECONDLY = "secondly"


SUPPORTED_SCHEDULE_MODES: tuple[ScheduleMode, ...] = tuple(ScheduleMode)


def coerce_schedule_mode(mode: ScheduleMode | str) -> ScheduleMode:
    """Convert a raw string or enum member into :class:`ScheduleMode`."""
    if isinstance(mode, ScheduleMode):
        return mode
    return ScheduleMode(mode)


def schedule_mode_from_raw(mode: object, *, default: ScheduleMode = ScheduleMode.DAILY) -> ScheduleMode:
    """Parse a persisted schedule mode and fall back to ``default`` on bad data."""
    if isinstance(mode, ScheduleMode):
        return mode
    try:
        return ScheduleMode(str(mode))
    except (TypeError, ValueError):
        return default


def schedule_mode_to_raw(mode: ScheduleMode | str) -> str:
    """Serialize a schedule mode back to the config-friendly string form."""
    return coerce_schedule_mode(mode).value

# Daily-mode scheduling uses datetime.now().astimezone() to be DST-aware.
# When the local timezone observes DST transitions, "daily at 14:30" stays
# anchored to the wall-clock hour rather than drifting by an hour twice a year.
def _local_now() -> datetime:
    """Return the current local time as a timezone-aware datetime."""
    return datetime.now().astimezone()


def schedule_value_is_valid(mode: ScheduleMode | str, value: str) -> bool:
    """Validate that ``value`` matches the rules of the selected mode."""
    value = value.strip()
    if not value:
        return False
    try:
        selected_mode = coerce_schedule_mode(mode)
    except ValueError:
        return False

    match selected_mode:
        case ScheduleMode.DAILY:
            if not re.fullmatch(r"\d{1,2}:\d{2}", value):
                return False
            hour_text, minute_text = value.split(":")
            hour = int(hour_text)
            minute = int(minute_text)
            return 0 <= hour <= 23 and 0 <= minute <= 59
        case ScheduleMode.HOURLY | ScheduleMode.MINUTELY | ScheduleMode.SECONDLY:
            return value.isdigit() and int(value) >= 1
    return False


class SyncScheduler(QObject):
    """Qt timer wrapper that emits export triggers on a configured cadence."""

    trigger = Signal()
    next_run_changed = Signal(object)  # datetime | None

    def __init__(self, parent=None, *, now_func=_local_now) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        self._mode: ScheduleMode | None = None
        self._value: str | None = None
        self._next_run: datetime | None = None
        self._now = now_func

    def configure(self, mode: ScheduleMode | str, value: str) -> None:
        """Store a validated recurrence mode/value pair for later start()."""
        selected_mode = coerce_schedule_mode(mode)
        if not schedule_value_is_valid(selected_mode, value):
            raise ValueError(f"Invalid value for {selected_mode.value!r}: {value!r}")
        self._mode = selected_mode
        self._value = value

    def start(self) -> None:
        """Arm the timer and emit the first calculated ``next_run``."""
        self._timer.stop()
        fast = os.environ.get("IDENTBRIDGE_FAST_TRIGGER_SECONDS")
        if fast and fast.strip().lstrip("-").isdigit() and int(fast) > 0:
            seconds = int(fast)
            _log.warning(
                "FAST_TRIGGER mode active: firing every %d seconds (dev only)",
                seconds,
            )
            # Disconnect the single-shot _fire callback; use direct trigger.emit
            try:
                self._timer.timeout.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._timer.setSingleShot(False)
            self._timer.setInterval(seconds * 1000)
            self._timer.timeout.connect(self.trigger.emit)
            self._timer.start()
            self._next_run = datetime.now().astimezone() + timedelta(seconds=seconds)
            self.next_run_changed.emit(self._next_run)
            return
        # Normal path: single-shot timer managed by _schedule_next / _fire
        # Ensure the timer is back in single-shot mode (in case start() was
        # previously called with FAST_TRIGGER and is now called without it).
        try:
            self._timer.timeout.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        self._next_run = None
        self.next_run_changed.emit(None)
        self._schedule_next()

    def stop(self) -> None:
        """Stop scheduling and clear the cached next-run timestamp."""
        self._timer.stop()
        self._next_run = None
        self.next_run_changed.emit(None)

    def next_run(self) -> datetime | None:
        """Return the currently scheduled run time, if any."""
        return self._next_run

    def _schedule_next(self) -> None:
        if self._mode is None or self._value is None:
            return  # configure() не был вызван до start()

        now = self._now()
        self._next_run = self._calculate_next_run(now)
        self.next_run_changed.emit(self._next_run)
        delay = max(1.0, (self._next_run - now).total_seconds())

        self._timer.start(int(delay * 1000))

    def _fire(self) -> None:
        scheduled_for = self._next_run
        self.trigger.emit()
        if scheduled_for is not None:
            self._next_run = scheduled_for
        self._schedule_next()

    def _calculate_next_run(self, now: datetime) -> datetime:
        if self._mode is None or self._value is None:
            raise RuntimeError("Scheduler is not configured")

        match self._mode:
            case ScheduleMode.DAILY:
                return self._next_daily_run(now)
            case ScheduleMode.HOURLY | ScheduleMode.MINUTELY | ScheduleMode.SECONDLY:
                return self._next_interval_run(now)
        raise RuntimeError(f"Unsupported schedule mode: {self._mode!r}")

    def _next_daily_run(self, now: datetime) -> datetime:
        hour_text, minute_text = self._value.split(":")
        if self._next_run is not None:
            candidate = self._next_run + timedelta(days=1)
        else:
            candidate = now.replace(
                hour=int(hour_text),
                minute=int(minute_text),
                second=0,
                microsecond=0,
            )
            if candidate <= now:
                candidate += timedelta(days=1)

        while candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    def _next_interval_run(self, now: datetime) -> datetime:
        step = self._interval_step()
        candidate = (self._next_run + step) if self._next_run is not None else (now + step)
        while candidate <= now:
            candidate += step
        return candidate

    def _interval_step(self) -> timedelta:
        if self._mode is None or self._value is None:
            raise RuntimeError("Scheduler is not configured")

        amount = int(self._value)
        if amount < 1:
            raise RuntimeError(f"Invalid interval value: {self._value!r}")

        match self._mode:
            case ScheduleMode.SECONDLY:
                return timedelta(seconds=amount)
            case ScheduleMode.MINUTELY:
                return timedelta(minutes=amount)
            case ScheduleMode.HOURLY:
                return timedelta(hours=amount)
            case _:
                raise RuntimeError(f"Mode {self._mode!r} is not interval-based")
