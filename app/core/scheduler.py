import random
from datetime import datetime, timedelta
from typing import Literal

from PySide6.QtCore import QObject, QTimer, Signal


# Daily-mode scheduling uses datetime.now().astimezone() to be DST-aware.
# When the local timezone observes DST transitions, "daily at 14:30" stays
# anchored to the wall-clock hour rather than drifting by an hour twice a year.
def _local_now() -> datetime:
    """Return the current local time as a timezone-aware datetime."""
    return datetime.now().astimezone()


class SyncScheduler(QObject):
    trigger = Signal()
    next_run_changed = Signal(object)  # datetime | None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fire)
        self._mode: Literal["daily", "hourly", "cron"] | None = None
        self._value: str | None = None
        self._next_run: datetime | None = None

    def configure(self, mode: Literal["daily", "hourly", "cron"], value: str) -> None:
        self._mode = mode
        self._value = value

    def start(self) -> None:
        self.stop()
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

        if self._mode == "daily":
            parts = self._value.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate += timedelta(days=1)
            base_delay = (candidate - now).total_seconds()

        elif self._mode == "hourly":
            base_delay = int(self._value) * 3600

        elif self._mode == "cron":
            raise NotImplementedError("cron mode is not implemented")

        else:
            raise ValueError(f"Unknown mode: {self._mode!r}")

        jitter = random.uniform(-base_delay * 0.05, base_delay * 0.05)
        delay = max(1.0, base_delay + jitter)

        self._next_run = now + timedelta(seconds=delay)
        self.next_run_changed.emit(self._next_run)

        self._timer.start(int(delay * 1000))

    def _fire(self) -> None:
        self.trigger.emit()
        self._schedule_next()
