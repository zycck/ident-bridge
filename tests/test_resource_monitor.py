"""Tests for app.core.resource_monitor."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from app.core import resource_monitor as rm_mod
from app.core.resource_monitor import ResourceMonitor, ResourceSample


# --- ResourceSample ------------------------------------------------------


def test_sample_is_frozen():
    s = ResourceSample(cpu_percent=1.5, rss_bytes=1_048_576, handles=100, threads=4)
    with pytest.raises((AttributeError, TypeError)):
        s.cpu_percent = 2.0  # type: ignore[misc]


def test_sample_rss_mib_conversion():
    s = ResourceSample(cpu_percent=0.0, rss_bytes=2 * 1024 * 1024, handles=0, threads=1)
    assert s.rss_mib == pytest.approx(2.0)


# --- ResourceMonitor helper stubs ---------------------------------------


@dataclass
class _FakeMemInfo:
    rss: int


class _FakeProcess:
    """Minimal psutil.Process stand-in for deterministic tests."""

    def __init__(self) -> None:
        self._cpu_ticks = [0.0, 3.5, 7.2]  # successive cpu_percent() returns
        self._cpu_idx = 0
        self._handles = 321
        self._threads = 9
        self._rss = 50 * 1024 * 1024

    def cpu_percent(self, interval=None) -> float:
        v = self._cpu_ticks[min(self._cpu_idx, len(self._cpu_ticks) - 1)]
        self._cpu_idx += 1
        return v

    def memory_info(self) -> _FakeMemInfo:
        return _FakeMemInfo(rss=self._rss)

    def num_threads(self) -> int:
        return self._threads

    def num_handles(self) -> int:
        return self._handles

    def oneshot(self):
        class _Ctx:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *a):
                return False

        return _Ctx()


class _FakePsutil:
    Error = type("Error", (Exception,), {})

    def __init__(self, proc: _FakeProcess) -> None:
        self._proc = proc

    def Process(self, pid: int) -> _FakeProcess:  # noqa: N802 (mirror psutil API)
        return self._proc


@pytest.fixture
def fake_psutil(monkeypatch):
    proc = _FakeProcess()
    fake = _FakePsutil(proc)
    monkeypatch.setattr(rm_mod, "_psutil", fake)
    return fake, proc


# --- ResourceMonitor tests ----------------------------------------------


def test_monitor_reports_available_when_psutil_present(qtbot, fake_psutil):
    mon = ResourceMonitor(interval_ms=5)
    assert mon.is_available() is True


def test_monitor_collects_sample(qtbot, fake_psutil):
    mon = ResourceMonitor(interval_ms=5)
    sample = mon.current()
    assert sample is not None
    assert sample.handles == 321
    assert sample.threads == 9
    assert sample.rss_bytes == 50 * 1024 * 1024
    assert sample.cpu_percent >= 0.0


def test_monitor_emits_signal_on_tick(qtbot, fake_psutil):
    mon = ResourceMonitor(interval_ms=5)
    received: list = []
    mon.sample.connect(received.append)
    mon.start()
    qtbot.waitUntil(lambda: len(received) >= 2, timeout=2000)
    mon.stop()
    first = received[0]
    assert isinstance(first, ResourceSample)
    assert first.threads == 9


def test_monitor_start_is_noop_when_psutil_missing(qtbot, monkeypatch):
    monkeypatch.setattr(rm_mod, "_psutil", None)
    mon = ResourceMonitor(interval_ms=5)
    assert mon.is_available() is False
    mon.start()  # must not raise
    assert mon.is_active() is False
    assert mon.current() is None


def test_monitor_interval_updates(qtbot, fake_psutil):
    mon = ResourceMonitor(interval_ms=500)
    assert mon.interval_ms == 500
    mon.set_interval_ms(250)
    assert mon.interval_ms == 250


def test_monitor_stop_is_idempotent(qtbot, fake_psutil):
    mon = ResourceMonitor(interval_ms=5)
    mon.stop()
    mon.stop()  # must not raise


def test_monitor_num_handles_absent_returns_zero(qtbot, monkeypatch):
    proc = _FakeProcess()
    del type(proc).num_handles  # type: ignore[misc]
    # Rebuild fake without num_handles attr
    class _NoHandlesProc(_FakeProcess):
        pass
    _NoHandlesProc.num_handles = property(lambda self: (_ for _ in ()).throw(AttributeError))  # type: ignore

    class _FakePsutilNoHandles:
        Error = type("Error", (Exception,), {})

        def Process(self, pid):  # noqa: N802
            p = _FakeProcess()
            # Simulate absence of num_handles (Linux/mac)
            p.__dict__.pop("num_handles", None)
            type_cls = type("ProcNoHandles", (), {
                "cpu_percent": lambda self_inner, interval=None: 0.0,
                "memory_info": lambda self_inner: _FakeMemInfo(rss=1024),
                "num_threads": lambda self_inner: 1,
                "oneshot": lambda self_inner: __import__("contextlib").nullcontext(),
            })
            return type_cls()

    monkeypatch.setattr(rm_mod, "_psutil", _FakePsutilNoHandles())
    mon = ResourceMonitor(interval_ms=5)
    s = mon.current()
    assert s is not None
    assert s.handles == 0
