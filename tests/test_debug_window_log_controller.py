# -*- coding: utf-8 -*-
"""Tests for extracted DebugWindow log bridge."""

from app.ui.debug_window_log_controller import DebugWindowLogController


class _FakeSignal:
    def __init__(self) -> None:
        self._callbacks: list = []

    def connect(self, callback) -> None:
        self._callbacks.append(callback)

    def disconnect(self, callback) -> None:
        self._callbacks.remove(callback)

    def emit(self, *args) -> None:
        for callback in list(self._callbacks):
            callback(*args)


class _FakeHandler:
    def __init__(self, history: list[str]) -> None:
        self.history = list(history)
        self.message = _FakeSignal()


def test_debug_window_log_controller_replays_history_once_and_streams_live() -> None:
    handler = _FakeHandler(["one", "two"])
    seen: list[str] = []
    controller = DebugWindowLogController(
        on_message=seen.append,
        get_handler_fn=lambda: handler,
    )

    controller.connect()
    controller.connect()
    handler.message.emit("live")

    assert seen == ["one", "two", "live"]


def test_debug_window_log_controller_disconnect_stops_live_feed() -> None:
    handler = _FakeHandler([])
    seen: list[str] = []
    controller = DebugWindowLogController(
        on_message=seen.append,
        get_handler_fn=lambda: handler,
    )

    controller.connect()
    controller.disconnect()
    handler.message.emit("after")

    assert seen == []
