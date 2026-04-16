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
