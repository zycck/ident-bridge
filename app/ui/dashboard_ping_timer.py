# -*- coding: utf-8 -*-
"""Timer lifecycle helper for dashboard connectivity pings."""

from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer


class DashboardPingTimerController(QObject):
    def __init__(
        self,
        *,
        parent: QObject,
        ping: Callable[[], None],
        interval_ms: int,
        timer_factory=QTimer,
        single_shot=None,
    ) -> None:
        super().__init__(parent)
        self._ping = ping
        self._interval_ms = interval_ms
        self._timer_factory = timer_factory
        self._single_shot = single_shot or QTimer.singleShot
        self._timer = None

    def start(self) -> None:
        if self._timer is None:
            self._timer = self._timer_factory(self)
            self._timer.setInterval(self._interval_ms)
            self._timer.timeout.connect(self._ping)
        self._timer.start()
        self._single_shot(1500, self._ping)

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

