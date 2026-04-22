"""Tests for extracted export SQL panel widget."""

from app.export.sql_templates import get_export_job_sql_template
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

    assert valid_text == "\u2713 SQL"
    assert invalid_text.startswith("\u2717 ")


def test_sql_panel_clears_empty_syntax_state(qtbot) -> None:
    panel = ExportSqlPanel()
    qtbot.addWidget(panel)

    panel.set_sql_text("")
    panel.refresh_syntax()

    assert panel._syntax_lbl.text() == ""
    assert panel._syntax_lbl.toolTip() == ""


def test_sql_panel_applies_payroll_template_and_emits_change(qtbot) -> None:
    panel = ExportSqlPanel()
    qtbot.addWidget(panel)

    changed = []
    panel.changed.connect(lambda: changed.append(True))

    panel._apply_template("payroll_directory")

    assert "employee_id" in panel.sql_text()
    assert "[\u0421\u043e\u0442\u0440\u0443\u0434\u043d\u0438\u043a]" in panel.sql_text()
    assert changed == [True]


def test_sql_panel_exposes_payroll_template_actions() -> None:
    panel = ExportSqlPanel()

    action_texts = [action.text() for action in panel._template_actions.values()]

    assert action_texts == [
        get_export_job_sql_template("payroll_directory").label,
        get_export_job_sql_template("payroll_accruals_rate_1").label,
        get_export_job_sql_template("payroll_accruals_rate_2").label,
    ]
