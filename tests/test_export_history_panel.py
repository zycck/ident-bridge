# -*- coding: utf-8 -*-
"""Tests for extracted export history panel."""

from PySide6.QtWidgets import QMessageBox

from app.ui.export_history_panel import ExportHistoryPanel


def _sample_entry(*, ts: str = "2026-04-16 12:00:00", ok: bool = True) -> dict:
    return {
        "ts": ts,
        "trigger": "manual",
        "ok": ok,
        "rows": 3,
        "err": "",
    }


def test_history_panel_shows_and_tracks_entries(qtbot) -> None:
    panel = ExportHistoryPanel()
    qtbot.addWidget(panel)
    panel.show()

    panel.prepend_entry(_sample_entry())

    assert len(panel.history()) == 1
    assert panel.latest_entry() is not None
    assert panel._history_hdr.text() == "История (1)"
    assert panel._history_scroll.isVisible() is True


def test_history_panel_delete_requested_removes_entry(qtbot) -> None:
    panel = ExportHistoryPanel()
    qtbot.addWidget(panel)
    panel.set_history([_sample_entry(), _sample_entry(ts="2026-04-16 12:01:00")])

    panel._delete_history(0)

    assert len(panel.history()) == 1
    assert panel.history()[0]["ts"] == "2026-04-16 12:01:00"


def test_history_panel_clear_confirms_before_removing(monkeypatch, qtbot) -> None:
    panel = ExportHistoryPanel()
    qtbot.addWidget(panel)
    panel.set_history([_sample_entry()])

    monkeypatch.setattr(
        "app.ui.export_history_panel.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    panel._on_clear_history()

    assert panel.history() == []


# --- Incremental behaviour (audit C1 / J5) ------------------------------


def test_prepend_entry_adds_single_widget(qtbot) -> None:
    panel = ExportHistoryPanel()
    qtbot.addWidget(panel)

    panel.prepend_entry(_sample_entry(ts="2026-04-16 12:00:00"))
    panel.prepend_entry(_sample_entry(ts="2026-04-16 12:01:00"))

    assert len(panel._row_widgets) == 2
    assert panel._history[0]["ts"] == "2026-04-16 12:01:00"
    # Layout count should match widget list (no stale QLayoutItems)
    assert panel._history_layout.count() == 2


def test_prepend_respects_history_max(qtbot, monkeypatch) -> None:
    from app.ui import export_history_panel as mod

    monkeypatch.setattr(mod, "HISTORY_MAX", 3)
    panel = ExportHistoryPanel()
    qtbot.addWidget(panel)

    for i in range(5):
        panel.prepend_entry(_sample_entry(ts=f"2026-04-16 12:{i:02d}:00"))

    assert len(panel._history) == 3
    assert len(panel._row_widgets) == 3
    # Most recent stays on top
    assert panel._history[0]["ts"] == "2026-04-16 12:04:00"
    # Oldest two evicted
    assert panel._history[-1]["ts"] == "2026-04-16 12:02:00"


def test_delete_reindexes_remaining_rows(qtbot) -> None:
    panel = ExportHistoryPanel()
    qtbot.addWidget(panel)
    panel.set_history([
        _sample_entry(ts="2026-04-16 12:00:00"),
        _sample_entry(ts="2026-04-16 12:01:00"),
        _sample_entry(ts="2026-04-16 12:02:00"),
    ])

    # Delete the middle one
    panel._delete_history(1)

    assert len(panel._row_widgets) == 2
    assert [r._index for r in panel._row_widgets] == [0, 1]
    # Next delete of index 1 should remove the one that's now at position 1
    panel._delete_history(1)
    assert len(panel._history) == 1
    assert panel._history[0]["ts"] == "2026-04-16 12:00:00"


def test_set_history_resets_widgets(qtbot) -> None:
    panel = ExportHistoryPanel()
    qtbot.addWidget(panel)
    panel.prepend_entry(_sample_entry())
    panel.prepend_entry(_sample_entry(ts="2026-04-16 12:01:00"))
    assert len(panel._row_widgets) == 2

    panel.set_history([_sample_entry(ts="2026-04-16 12:05:00")])

    assert len(panel._row_widgets) == 1
    assert panel._history_layout.count() == 1
    assert panel._history[0]["ts"] == "2026-04-16 12:05:00"
