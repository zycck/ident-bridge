"""Tests for app.ui.resource_monitor_bar.ResourceMonitorBar."""

from __future__ import annotations

import pytest

from app.core.resource_monitor import ResourceMonitor, ResourceSample
from app.ui.resource_monitor_bar import ResourceMonitorBar, _sparkline


def test_sparkline_empty_returns_empty_string():
    assert _sparkline([]) == ""


def test_sparkline_length_matches_samples():
    out = _sparkline([1.0, 2.0, 3.0, 4.0, 5.0])
    assert len(out) == 5


def test_sparkline_respects_max_value_ceiling():
    # value equal to max_value → top block; half → middle-ish block
    out_top = _sparkline([100.0], max_value=100.0)
    assert out_top == "\u2588"  # full block
    out_low = _sparkline([0.0], max_value=100.0)
    assert out_low == "\u2581"  # lowest block
    out_half = _sparkline([50.0], max_value=100.0)
    # somewhere in the middle of the 8-block palette
    assert "\u2583" <= out_half <= "\u2586"


def test_bar_shows_placeholder_before_any_sample(qtbot):
    mon = ResourceMonitor(interval_ms=5)
    bar = ResourceMonitorBar(mon)
    qtbot.addWidget(bar)
    assert bar._cpu_label.text().startswith("CPU")
    assert bar._ram_label.text().startswith("RAM")


def test_bar_updates_on_signal(qtbot):
    mon = ResourceMonitor(interval_ms=5)
    bar = ResourceMonitorBar(mon)
    qtbot.addWidget(bar)
    sample = ResourceSample(
        cpu_percent=12.5,
        rss_bytes=256 * 1024 * 1024,
        handles=321,
        threads=9,
    )
    mon.sample.emit(sample)
    assert "12.5" in bar._cpu_label.text()
    assert "256.0" in bar._ram_label.text()
    assert bar._handles_label.text() == "H 321"
    assert bar._threads_label.text() == "T 9"


def test_bar_ignores_non_sample_payload(qtbot):
    mon = ResourceMonitor(interval_ms=5)
    bar = ResourceMonitorBar(mon)
    qtbot.addWidget(bar)
    prev = bar._cpu_label.text()
    mon.sample.emit("not a sample")
    assert bar._cpu_label.text() == prev


def test_bar_announces_unavailability(qtbot, monkeypatch):
    from app.core import resource_monitor as rm_mod
    monkeypatch.setattr(rm_mod, "_psutil", None)
    mon = ResourceMonitor(interval_ms=5)
    bar = ResourceMonitorBar(mon)
    qtbot.addWidget(bar)
    assert "psutil unavailable" in bar._cpu_label.text()
