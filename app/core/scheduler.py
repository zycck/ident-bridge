import logging
import os
import random
import re
from datetime import datetime, timedelta
from enum import StrEnum, UNIQUE, verify

from PySide6.QtCore import QObject, QTimer, Signal

_log = logging.getLogger(__name__)


@verify(UNIQUE)
class ScheduleMode(StrEnum):
    DAILY = "daily"
    HOURLY = "hourly"
    MINUTELY = "minutely"
    SECONDLY = "secondly"


SUPPORTED_SCHEDULE_MODES: tuple[ScheduleMode, ...] = tuple(ScheduleMode)


def coerce_schedule_mode(mode: ScheduleMode | str) -> ScheduleMode:
    if isinstance(mode, ScheduleMode):
        return mode
    return ScheduleMode(mode)


def schedule_mode_from_raw(mode: object, *, default: ScheduleMode = ScheduleMode.DAILY) -> ScheduleMode:
    if isinstance(mode, ScheduleMode):
        return mode
    try:
        return ScheduleMode(str(mode))
    except (TypeError, ValueError):
        return default


def schedule_mode_to_raw(mode: ScheduleMode | str) -> str:
    return coerce_schedule_mode(mode).value

# Daily-mode scheduling uses datetime.now().astimezone() to be DST-aware.
# When the local timezone observes DST transitions, "daily at 14:30" stays
# anchored to the wall-clock hour rather than drifting by an hour twice a year.
def _local_now() -> datetime:
    """Return the current local time as a timezone-aware datetime."""
    return datetime.now().astimezone()


def schedule_value_is_valid(mode: ScheduleMode | str, value: str) -> bool:
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
    trigger = Signal()
    next_run_changed = Signal(object)  # datetime | None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        self._mode: ScheduleMode | None = None
        self._value: str | None = None
        self._next_run: datetime | None = None

    def configure(self, mode: ScheduleMode | str, value: str) -> None:
        selected_mode = coerce_schedule_mode(mode)
        if not schedule_value_is_valid(selected_mode, value):
            raise ValueError(f"Invalid value for {selected_mode.value!r}: {value!r}")
        self._mode = selected_mode
        self._value = value

    def start(self) -> None:
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
        self._timer.stop()
        self._next_run = None
        self.next_run_changed.emit(None)

    def next_run(self) -> datetime | None:
        return self._next_run

    def _schedule_next(self) -> None:
        if self._mode is None or self._value is None:
            return  # configure() не был вызван до start()

        now = _local_now()

        match self._mode:
            case ScheduleMode.SECONDLY:
                n = int(self._value)
                if n < 1:
                    return
                base_delay = float(n)
            case ScheduleMode.MINUTELY:
                n = int(self._value)
                if n < 1:
                    return
                base_delay = n * 60.0
            case ScheduleMode.HOURLY:
                n = int(self._value)
                if n < 1:
                    return
                base_delay = n * 3600.0
            case ScheduleMode.DAILY:
                hour_text, minute_text = self._value.split(":")
                candidate = now.replace(
                    hour=int(hour_text),
                    minute=int(minute_text),
                    second=0,
                    microsecond=0,
                )
                if candidate <= now:
                    candidate += timedelta(days=1)
                base_delay = (candidate - now).total_seconds()

        jitter = random.uniform(-base_delay * 0.05, base_delay * 0.05)
        delay = max(1.0, base_delay + jitter)

        self._next_run = now + timedelta(seconds=delay)
        self.next_run_changed.emit(self._next_run)

        self._timer.start(int(delay * 1000))

    def _fire(self) -> None:
        self.trigger.emit()
        self._schedule_next()
