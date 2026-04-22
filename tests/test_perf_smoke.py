"""Tests for tracemalloc performance smoke harness."""

import weakref

from PySide6.QtWidgets import QWidget

from tools import perf_smoke


def test_perf_smoke_registers_recent_ui_scenarios() -> None:
    assert "export-editor" in perf_smoke.SCENARIOS
    assert "settings-widget" in perf_smoke.SCENARIOS
    assert "test-run-dialog" in perf_smoke.SCENARIOS
    assert "gas-chunking" in perf_smoke.SCENARIOS


def test_perf_smoke_run_cycles_executes_selected_scenarios(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        perf_smoke,
        "SCENARIOS",
        {
            "alpha": lambda app, iteration: calls.append(("alpha", iteration)),
            "beta": lambda app, iteration: calls.append(("beta", iteration)),
        },
    )
    monkeypatch.setattr(perf_smoke, "gc", type("GC", (), {"collect": staticmethod(lambda: None)})())
    monkeypatch.setattr(perf_smoke, "_process_events", lambda app, rounds=6: None)

    perf_smoke._run_cycles(app=object(), scenario="alpha", cycles=2)
    assert calls == [("alpha", 0), ("alpha", 1)]

    calls.clear()
    perf_smoke._run_cycles(app=object(), scenario="all", cycles=1)
    assert calls == [("alpha", 0), ("beta", 0)]


def test_perf_smoke_dispose_widget_flushes_deferred_delete(qapp_session) -> None:
    widget = QWidget()
    ref = weakref.ref(widget)

    perf_smoke._dispose_widget(widget, qapp_session)
    widget = None

    assert ref() is None
