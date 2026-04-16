# -*- coding: utf-8 -*-
"""Tests for extracted export SQL panel widget."""

from app.ui.export_sql_panel import ExportSqlPanel


def test_sql_panel_roundtrips_text_and_emits_change(qtbot) -> None:
    panel = ExportSqlPanel()
    qtbot.addWidget(panel)

    changed = []
    panel.changed.connect(lambda: changed.append(True))

    panel._query_edit.setPlainText("SELECT 1")

    assert panel.sql_text() == "SELECT 1"
    assert changed == [True]


def test_sql_panel_refreshes_syntax_state(qtbot) -> None:
    panel = ExportSqlPanel()
    qtbot.addWidget(panel)

    panel.set_sql_text("SELECT 1")
    panel.refresh_syntax()
    valid_text = panel._syntax_lbl.text()

    panel.set_sql_text("SELECT FROM")
    panel.refresh_syntax()
    invalid_text = panel._syntax_lbl.text()

    assert valid_text == "✓ SQL"
    assert invalid_text.startswith("✗ ")


def test_sql_panel_clears_empty_syntax_state(qtbot) -> None:
    panel = ExportSqlPanel()
    qtbot.addWidget(panel)

    panel.set_sql_text("")
    panel.refresh_syntax()

    assert panel._syntax_lbl.text() == ""
    assert panel._syntax_lbl.toolTip() == ""
