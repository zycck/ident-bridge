# -*- coding: utf-8 -*-
"""
QThread + worker factory.

Eliminates ~120 lines of boilerplate scattered across every widget that
spawns a background worker. Handles the standard PySide6 GC-pin pattern
(self.<attr> = worker) and identity-safe cleanup on thread.finished.
"""
import weakref
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, QTimer


def run_worker(
    parent: QObject,
    worker: QObject,
    *,
    pin_attr: str | None = None,
    on_finished: Callable[..., Any] | None = None,
    on_error: Callable[[str], None] | None = None,
    entry: str = "run",
) -> QThread:
    """
    Move *worker* to a new QThread, wire cleanup, start, return the thread.

    PySide6 needs an explicit Python reference to keep workers alive (Shiboken
    ownership semantics). Pass `pin_attr` to assign the worker to
    `parent.<pin_attr>`; the helper clears that attribute on `thread.finished`,
    identity-safely so a re-entered slot does not nuke a fresh worker.

    Workers with `finished` and/or `error` signals get those wired to
    `thread.quit` automatically. Optional `on_finished` / `on_error` callbacks
    let callers handle results without manual wiring.

    The actual thread start is deferred to the next event-loop turn via
    `QTimer.singleShot(0, ...)`. This gives callers a safe window to attach
    additional non-terminal signals after `run_worker()` returns, which avoids
    late-connect races for fast workers.

    For workers whose entry-point method is not named `run`, pass a different
    name via `entry`. If the method does not exist, the helper silently skips
    the connection (caller may invoke it manually after `thread.start()`).
    """
    thread = QThread(parent)
    worker.moveToThread(thread)

    started_slot = getattr(worker, entry, None)
    if started_slot is not None:
        thread.started.connect(started_slot)

    if hasattr(worker, "finished"):
        worker.finished.connect(thread.quit)  # type: ignore[attr-defined]
        if on_finished is not None:
            worker.finished.connect(on_finished)  # type: ignore[attr-defined]

    if hasattr(worker, "error"):
        worker.error.connect(thread.quit)  # type: ignore[attr-defined]
        if on_error is not None:
            worker.error.connect(on_error)  # type: ignore[attr-defined]

    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    if pin_attr is not None:
        setattr(parent, pin_attr, worker)
        parent_ref = weakref.ref(parent)

        def _clear() -> None:
            p = parent_ref()
            if p is None:
                return  # parent was garbage-collected
            # Bypass getattr/setattr (which can fail on dead Shiboken
            # wrappers) and write directly into __dict__. Identity check
            # via __dict__.get prevents nuking a fresh worker that was
            # pinned to the same attribute after this one finished.
            try:
                if p.__dict__.get(pin_attr) is worker:
                    p.__dict__[pin_attr] = None
            except (RuntimeError, AttributeError, TypeError):
                # Final fallback: try the regular setattr path
                try:
                    setattr(p, pin_attr, None)
                except Exception:
                    pass

        thread.finished.connect(_clear)

    # Start on the next event-loop turn so callers can safely connect extra
    # signals after `run_worker()` returns.
    QTimer.singleShot(0, thread.start)
    return thread
