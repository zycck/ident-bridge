# -*- coding: utf-8 -*-
"""
QThread + worker factory.

Eliminates ~120 lines of boilerplate scattered across every widget that
spawns a background worker. Handles the standard PySide6 GC-pin pattern
(self.<attr> = worker) and identity-safe cleanup on thread.finished.
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QThread


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

        def _clear() -> None:
            if getattr(parent, pin_attr, None) is worker:
                setattr(parent, pin_attr, None)

        thread.finished.connect(_clear)

    thread.start()
    return thread
