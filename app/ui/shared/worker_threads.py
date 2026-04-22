"""
QThread + worker factory.

Eliminates boilerplate around background Qt workers, keeps active threads
alive independently from short-lived widgets, and provides bounded shutdown
helpers for application exit.
"""

import inspect
import weakref
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer
from PySide6.QtWidgets import QApplication

_ALL_THREADS: set[QThread] = set()


class _CallbackDispatcher(QObject):
    def __init__(
        self,
        *,
        on_finished: Callable[..., Any] | None,
        on_error: Callable[..., Any] | None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_finished = on_finished
        self._on_error = on_error

    def on_finished(self, *args: Any) -> None:
        callback = self._on_finished
        if callback is None:
            return
        callback(*args)

    def on_error(self, *args: Any) -> None:
        callback = self._on_error
        if callback is None:
            return
        callback(*args)


def _safe_callback(callback: Callable[..., Any] | None) -> Callable[..., Any] | None:
    if callback is None:
        return None

    try:
        if inspect.ismethod(callback):
            ref = weakref.WeakMethod(callback)

            def _wrapped(*args: Any) -> Any:
                current = ref()
                if current is None:
                    return None
                try:
                    return current(*args)
                except RuntimeError:
                    return None

            return _wrapped
    except TypeError:
        return callback

    return callback


def _owner_threads(owner: QObject) -> set[QThread]:
    threads = owner.__dict__.get("_worker_threads")
    if not isinstance(threads, set):
        threads = set()
        owner.__dict__["_worker_threads"] = threads
    return threads


def _register_thread(owner: QObject, thread: QThread) -> None:
    _ALL_THREADS.add(thread)
    _owner_threads(owner).add(thread)

    owner_ref = weakref.ref(owner)

    def _clear() -> None:
        _ALL_THREADS.discard(thread)
        current_owner = owner_ref()
        if current_owner is None:
            return
        try:
            _owner_threads(current_owner).discard(thread)
        except RuntimeError:
            return

    thread.finished.connect(_clear)


def _shutdown_threads(threads: list[QThread], *, wait_ms: int) -> None:
    for thread in threads:
        try:
            if not thread.isRunning():
                continue
        except RuntimeError:
            continue
        thread.requestInterruption()
        thread.quit()

    for thread in threads:
        try:
            if thread.isRunning():
                thread.wait(wait_ms)
        except RuntimeError:
            continue


def shutdown_worker_threads(owner: QObject, *, wait_ms: int = 5_000) -> None:
    _shutdown_threads(list(_owner_threads(owner)), wait_ms=wait_ms)


def shutdown_all_worker_threads(*, wait_ms: int = 10_000) -> None:
    _shutdown_threads(list(_ALL_THREADS), wait_ms=wait_ms)


def run_worker(
    parent: QObject,
    worker: QObject,
    *,
    pin_attr: str | None = None,
    on_finished: Callable[..., Any] | None = None,
    on_error: Callable[[str], None] | None = None,
    connect_signals: Callable[[QObject, QThread], None] | None = None,
    entry: str = "run",
) -> QThread:
    """
    Move *worker* to a new QThread, wire cleanup, start, return the thread.

    PySide6 needs an explicit Python reference to keep workers alive.
    Pass `pin_attr` to assign the worker to `parent.<pin_attr>`; the helper
    clears that attribute on `thread.finished`, identity-safely so a re-entered
    slot does not nuke a fresh worker.

    Threads are parented to the QApplication instance instead of the owner
    widget. That prevents `QThread destroyed while thread still running` when
    a short-lived dialog/widget closes while work is still in flight.
    """
    thread = QThread(QApplication.instance())
    worker.moveToThread(thread)
    thread.__dict__["_worker_ref"] = worker
    _register_thread(parent, thread)

    started_slot = getattr(worker, entry, None)
    if started_slot is not None:
        thread.started.connect(started_slot)

    safe_finished = _safe_callback(on_finished)
    safe_error = _safe_callback(on_error)
    callback_dispatcher = _CallbackDispatcher(
        on_finished=safe_finished,
        on_error=safe_error,
        parent=QApplication.instance(),
    )
    thread.__dict__["_callback_dispatcher"] = callback_dispatcher

    if hasattr(worker, "finished"):
        worker.finished.connect(thread.quit)  # type: ignore[attr-defined]
        if safe_finished is not None:
            worker.finished.connect(callback_dispatcher.on_finished)  # type: ignore[attr-defined]

    if hasattr(worker, "error"):
        worker.error.connect(thread.quit)  # type: ignore[attr-defined]
        if safe_error is not None:
            worker.error.connect(callback_dispatcher.on_error)  # type: ignore[attr-defined]

    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda: thread.__dict__.pop("_worker_ref", None))
    thread.finished.connect(lambda: thread.__dict__.pop("_callback_dispatcher", None))

    if pin_attr is not None:
        setattr(parent, pin_attr, worker)
        parent_ref = weakref.ref(parent)

        def _clear_pin() -> None:
            current_parent = parent_ref()
            if current_parent is None:
                return
            try:
                if current_parent.__dict__.get(pin_attr) is worker:
                    current_parent.__dict__[pin_attr] = None
            except (RuntimeError, AttributeError, TypeError):
                try:
                    setattr(current_parent, pin_attr, None)
                except Exception:
                    return

        thread.finished.connect(_clear_pin)

    if connect_signals is not None:
        connect_signals(worker, thread)

    QTimer.singleShot(0, thread.start)
    return thread


__all__ = [
    "run_worker",
    "shutdown_all_worker_threads",
    "shutdown_worker_threads",
]
