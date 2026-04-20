"""Tests for extracted export editor shell/view."""

from app.ui.export_editor_shell import ExportEditorShell


def test_export_editor_shell_roundtrips_core_fields(qtbot) -> None:
    shell = ExportEditorShell()
    qtbot.addWidget(shell)

    shell.set_job_name("Nightly")
    shell.set_sql_text("SELECT 1")
    shell.set_webhook_url("https://example.com")
    shell.set_gas_options(
        sheet_name="Exports",
        header_row=2,
        dedupe_key_columns=["id", "updated_at"],
    )
    shell.set_schedule(True, "hourly", "4")

    assert shell.job_name() == "Nightly"
    assert shell.sql_text() == "SELECT 1"
    assert shell.webhook_url() == "https://example.com"
    assert shell.gas_sheet_name() == "Exports"
    assert shell.gas_header_row() == 2
    assert shell.gas_dedupe_key_columns() == ["id", "updated_at"]
    assert shell.schedule_enabled() is True
    assert shell.schedule_mode() == "hourly"
    assert shell.schedule_value() == "4"


def test_export_editor_shell_forwards_child_signals(qtbot) -> None:
    shell = ExportEditorShell()
    qtbot.addWidget(shell)

    changed = []
    query_changed = []
    schedule_changed = []
    history_changed = []
    test_requested = []
    run_requested = []
    shell.changed.connect(lambda: changed.append(True))
    shell.query_changed.connect(lambda: query_changed.append(True))
    shell.schedule_changed.connect(lambda: schedule_changed.append(True))
    shell.history_changed.connect(lambda: history_changed.append(True))
    shell.test_requested.connect(lambda: test_requested.append(True))
    shell.run_requested.connect(lambda: run_requested.append(True))

    shell._header.changed.emit()
    shell._webhook_edit.editingFinished.emit()
    shell._sql_panel.changed.emit()
    shell._schedule_panel.changed.emit()
    shell._history_panel.changed.emit()
    shell._header.test_requested.emit()
    shell._header.run_requested.emit()

    assert changed == [True, True]
    assert query_changed == [True]
    assert schedule_changed == [True]
    assert history_changed == [True]
    assert test_requested == [True]
    assert run_requested == [True]


def test_export_editor_shell_routes_status_progress_and_history_helpers(qtbot) -> None:
    shell = ExportEditorShell()
    qtbot.addWidget(shell)

    shell.set_status("ok", "Done")
    shell.set_progress_text("Работаем…")
    shell.set_run_enabled(False)
    shell.prepend_history_entry({"ts": "2026-04-16 12:00:00", "ok": True, "rows": 2})

    assert shell._header._status_summary.text() == "Done"
    assert shell._schedule_panel._progress_lbl.text() == "Работаем…"
    assert shell._header._run_btn.isEnabled() is False
    assert shell.latest_history_entry() is not None
