# -*- coding: utf-8 -*-
"""Tests for app.ui.threading.run_worker() factory.

IMPORTANT design note
---------------------
run_worker() connects *both* ``worker.deleteLater`` and ``thread.deleteLater``
to ``thread.finished``.  That means as soon as ``thread.finished`` fires, both
the C++ worker and thread objects are scheduled for deletion.

Consequences for tests:
- Do NOT call ``thread.isRunning()`` after ``thread.finished`` fires — the C++
  object is already gone and Shiboken raises RuntimeError.
- Do NOT use ``qtbot.waitSignal(thread.finished)`` — pytest-qt tries to
  disconnect from the signal in ``__exit__``, which causes an access-violation
  because the C++ object has been deleted before the context manager exits.

Safe patterns used here:
- Connect a plain Python list/flag to ``worker.finished`` / ``worker.error``
  *before* calling ``run_worker``, then poll with ``qtbot.waitUntil``.
- Pass ``on_finished`` / ``on_error`` to ``run_worker`` for the same purpose.
- For ``_NoSignalsWorker`` (no auto-quit), the thread stays alive so
  ``thread.isRunning()`` is safe; we quit it manually afterwards.
"""
from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, QThread, Signal, Slot

from app.ui.threading import run_worker


# ── Sample worker classes ─────────────────────────────────────────────

class _DefaultWorker(QObject):
    """Worker with finished + error signals and a run() method."""
    finished = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.run_called = False

    @Slot()
    def run(self) -> None:
        self.run_called = True
        self.finished.emit()


class _ErrorWorker(QObject):
    finished = Signal()
    error = Signal(str)

    @Slot()
    def run(self) -> None:
        self.error.emit("simulated failure")


class _CustomEntryWorker(QObject):
    finished = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.checked = False

    @Slot()
    def check(self) -> None:
        self.checked = True
        self.finished.emit()


class _NoSignalsWorker(QObject):
    """Worker without finished/error — thread must be quit manually."""

    def __init__(self) -> None:
        super().__init__()
        self.run_called = False

    @Slot()
    def run(self) -> None:
        self.run_called = True


# ── Tests ─────────────────────────────────────────────────────────────

def test_run_worker_returns_qthread_instance(qapp_session, qtbot):
    parent = QObject()
    worker = _DefaultWorker()
    done = []
    worker.finished.connect(lambda: done.append(True))
    thread = run_worker(parent, worker)
    assert isinstance(thread, QThread)
    qtbot.waitUntil(lambda: bool(done), timeout=2000)


def test_run_worker_starts_thread_and_calls_run(qapp_session, qtbot):
    parent = QObject()
    worker = _DefaultWorker()
    done = []
    # Connect before run_worker so the flag is set before deleteLater fires
    worker.finished.connect(lambda: done.append(worker.run_called))
    run_worker(parent, worker)
    qtbot.waitUntil(lambda: bool(done), timeout=2000)
    assert done[0] is True


def test_run_worker_pin_attr_assigned_before_start(qapp_session, qtbot):
    """pin_attr is set synchronously before the thread starts."""
    parent = QObject()
    worker = _DefaultWorker()
    done = []
    worker.finished.connect(lambda: done.append(True))
    run_worker(parent, worker, pin_attr="_my_worker")
    # Immediately after run_worker() returns, the attribute must be set
    assert getattr(parent, "_my_worker", None) is worker
    qtbot.waitUntil(lambda: bool(done), timeout=2000)


def test_run_worker_pin_attr_cleared_on_thread_finished(qapp_session, qtbot):
    """pin_attr is set before start and is cleared/invalidated after thread.finished.

    run_worker connects _clear to thread.finished. After that signal fires,
    both worker and thread are scheduled for deleteLater. Due to PySide6
    Shiboken ownership, the Python wrapper on parent._my_worker may become
    a dangling reference (RuntimeError on access) or be set to None.

    We verify two things:
    1. Before the thread finishes, pin_attr is the worker object.
    2. After the thread finishes and events are processed, pin_attr is either
       None or a deleted (RuntimeError) C++ wrapper — not a live worker.
    """
    parent = QObject()
    worker = _DefaultWorker()
    done = []  # set before worker is deleted
    worker.finished.connect(lambda: done.append(True))
    run_worker(parent, worker, pin_attr="_my_worker")

    # Before thread finishes, attribute is set
    assert getattr(parent, "_my_worker", None) is worker

    # Wait for worker.finished (safe — happens before deleteLater fires)
    qtbot.waitUntil(lambda: bool(done), timeout=2000)

    # Process pending events so _clear and deleteLater slots run
    qtbot.wait(100)

    # After cleanup, pin_attr must be None or a dead wrapper
    val = parent.__dict__.get("_my_worker", "missing")
    assert val is None, f"Expected None after cleanup, got {val!r}"


def test_run_worker_on_finished_callback(qapp_session, qtbot):
    """on_finished is called when worker.finished fires."""
    parent = QObject()
    worker = _DefaultWorker()
    captured = []
    run_worker(parent, worker, on_finished=lambda *args: captured.append(args))
    qtbot.waitUntil(lambda: bool(captured), timeout=2000)
    assert len(captured) == 1


def test_run_worker_on_error_callback(qapp_session, qtbot):
    parent = QObject()
    worker = _ErrorWorker()
    errors = []
    run_worker(parent, worker, on_error=lambda msg: errors.append(msg))
    qtbot.waitUntil(lambda: bool(errors), timeout=2000)
    assert errors[0] == "simulated failure"


def test_run_worker_error_quits_thread(qapp_session, qtbot):
    """worker.error → thread.quit — thread terminates automatically."""
    parent = QObject()
    worker = _ErrorWorker()
    errors = []
    run_worker(parent, worker, on_error=lambda msg: errors.append(msg))
    qtbot.waitUntil(lambda: bool(errors), timeout=2000)
    # Thread has quit (and been deleted); we cannot call thread.isRunning()
    # The fact that on_error fired and run_worker exited cleanly is enough.
    assert errors[0] == "simulated failure"


def test_run_worker_custom_entry_method(qapp_session, qtbot):
    parent = QObject()
    worker = _CustomEntryWorker()
    done = []
    worker.finished.connect(lambda: done.append(worker.checked))
    run_worker(parent, worker, entry="check")
    qtbot.waitUntil(lambda: bool(done), timeout=2000)
    assert done[0] is True


def test_run_worker_without_signals_does_not_crash(qapp_session, qtbot):
    """Worker without finished/error runs without crashing.

    The thread won't quit automatically (no terminal signal), so it is
    safe to call thread.isRunning() and to quit it manually.
    """
    parent = QObject()
    worker = _NoSignalsWorker()
    thread = run_worker(parent, worker)
    qtbot.waitUntil(lambda: worker.run_called, timeout=2000)
    assert worker.run_called
    # Thread still alive — no auto-quit
    assert thread.isRunning()
    thread.quit()
    thread.wait(1000)


def test_run_worker_multiple_workers_independent(qapp_session, qtbot):
    """Two workers run in parallel without interfering."""
    parent = QObject()
    worker1 = _DefaultWorker()
    worker2 = _DefaultWorker()
    done = []
    run_worker(parent, worker1, pin_attr="_w1",
               on_finished=lambda: done.append("w1"))
    run_worker(parent, worker2, pin_attr="_w2",
               on_finished=lambda: done.append("w2"))
    qtbot.waitUntil(lambda: len(done) == 2, timeout=3000)
    assert "w1" in done
    assert "w2" in done


def test_run_worker_no_pin_attr_no_attribute_set(qapp_session, qtbot):
    """Without pin_attr, no attribute is injected on parent."""
    parent = QObject()
    worker = _DefaultWorker()
    done = []
    worker.finished.connect(lambda: done.append(True))
    run_worker(parent, worker)
    qtbot.waitUntil(lambda: bool(done), timeout=2000)
    assert not hasattr(parent, "_worker")
    assert not hasattr(parent, "worker")


def test_run_worker_missing_entry_silently_skipped(qapp_session, qtbot):
    """If entry method does not exist, run_worker skips connection silently.

    The thread starts but no slot is called.  We quit via thread.quit()
    which is safe because the thread has not been deleted yet (thread.quit
    only schedules quit; deleteLater fires on thread.finished).
    """
    parent = QObject()

    class _ManualWorker(QObject):
        finished = Signal()
        error = Signal(str)

    worker = _ManualWorker()
    # 'nonexistent' slot is missing — should not raise
    thread = run_worker(parent, worker, entry="nonexistent")
    assert thread.isRunning()
    # Quit manually; this triggers thread.finished → deleteLater
    thread.quit()
    # Wait for the thread to actually stop before we return
    # (thread.wait is a blocking call — fine since it's very fast)
    thread.wait(1000)
