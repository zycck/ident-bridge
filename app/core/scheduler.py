from PySide6.QtCore import QObject, Signal
from typing import Literal
from datetime import datetime, timedelta
import threading
import random


class SyncScheduler(QObject):
    trigger = Signal()
    next_run_changed = Signal(object)

    _timer: threading.Timer | None
    _mode: Literal["daily", "hourly", "cron"] | None
    _value: str | None
    _next_run: datetime | None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._timer = None
        self._mode = None
        self._value = None
        self._next_run = None

    def configure(self, mode: Literal["daily", "hourly", "cron"], value: str) -> None:
        self._mode = mode
        self._value = value

    def start(self) -> None:
        if self._timer is not None:
            self.stop()
        self._schedule_next()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        self._next_run = None
        self.next_run_changed.emit(None)

    def next_run(self) -> datetime | None:
        return self._next_run

    def _schedule_next(self) -> None:
        now = datetime.now()

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

        self._timer = threading.Timer(delay, self._fire)
        self._timer.daemon = True
        self._timer.start()

    def _fire(self) -> None:
        self.trigger.emit()
        self._schedule_next()
