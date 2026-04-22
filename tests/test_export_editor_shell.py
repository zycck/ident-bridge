"""Tests for extracted export editor shell/view."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.core.scheduler import ScheduleMode
from app.export.run_store import ExportRunInfo
from app.ui.export_editor_shell import ExportEditorShell


class _FakeAcceptedWizard(QDialog):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(kwargs.get("parent"))
        self.args = args
        self.kwargs = kwargs

    def exec(self) -> int:
        return int(QDialog.DialogCode.Accepted)

    def selected_config(self) -> dict[str, str]:
        return {
            "webhook_url": "https://script.google.com/macros/s/library/exec",
        }


class _FakeRejectedWizard(_FakeAcceptedWizard):
    def exec(self) -> int:
        return int(QDialog.DialogCode.Rejected)


def _unfinished_run(
    *,
    run_id: str = "run-1",
    write_mode: str = "replace_all",
    total_chunks: int = 3,
    delivered_chunks: int = 1,
    delivered_rows: int = 3,
    total_rows: int = 9,
    status: str = "failed",
    last_error: str = "Сеть оборвалась",
) -> ExportRunInfo:
    return ExportRunInfo(
        run_id=run_id,
        job_id="job-1",
        job_name="Nightly",
        webhook_url="https://script.google.com/macros/s/demo/exec",
        sheet_name="Exports",
        source_id="job-1",
        write_mode=write_mode,
        export_date="2026-04-21",
        total_chunks=total_chunks,
        total_rows=total_rows,
        delivered_chunks=delivered_chunks,
        delivered_rows=delivered_rows,
        status=status,
        trigger="manual",
        created_at="2026-04-21T09:00:00+00:00",
        updated_at="2026-04-21T09:05:00+00:00",
        started_at="2026-04-21T09:00:10+00:00",
        finished_at=None,
        last_error=last_error,
        sql_duration_us=0,
        total_duration_us=0,
        supersedes_run_id=None,
    )


def test_export_editor_shell_roundtrips_core_fields(qtbot) -> None:
    shell = ExportEditorShell()
    qtbot.addWidget(shell)

    shell.set_job_name("Nightly")
    shell.set_sql_text("SELECT 1")
    shell.set_webhook_url("https://example.com")
    shell.set_gas_options(sheet_name="Exports", write_mode="replace_all")
    shell.set_schedule(True, ScheduleMode.HOURLY, "4")

    assert shell.job_name() == "Nightly"
    assert shell.sql_text() == "SELECT 1"
    assert shell.webhook_url() == "https://example.com"
    assert shell.gas_sheet_name() == "Exports"
    assert shell.gas_write_mode() == "replace_all"
    assert shell.schedule_enabled() is True
    assert shell.schedule_mode() is ScheduleMode.HOURLY
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
    shell.set_progress_text("Работаем...")
    shell.set_run_busy(True)
    shell.set_run_enabled(False)
    shell.prepend_history_entry({"ts": "2026-04-16 12:00:00", "ok": True, "rows": 2})

    assert shell._header._status_summary.text() == "Done"
    assert shell._schedule_panel._progress_lbl.text() == "Работаем..."
    assert shell._header._run_btn.is_busy() is True
    assert shell._header._run_btn.isEnabled() is False
    assert shell.latest_history_entry() is not None


def test_export_editor_shell_routes_unfinished_retry_and_reset(qtbot) -> None:
    shell = ExportEditorShell()
    qtbot.addWidget(shell)

    calls: list[tuple[str, str]] = []
    shell.set_unfinished_retry_handler(lambda run_id: calls.append(("retry", run_id)))
    shell.set_unfinished_reset_handler(lambda run_id: calls.append(("reset", run_id)) or True)
    shell.set_unfinished_runs([_unfinished_run()])

    assert [run.run_id for run in shell.unfinished_runs()] == ["run-1"]
    buttons = {button.text(): button for button in shell.findChildren(type(shell._gas_setup_wizard_btn))}
    assert "Повторить заново" in buttons
    assert "Сбросить" in buttons

    qtbot.mouseClick(buttons["Повторить заново"], Qt.MouseButton.LeftButton)
    qtbot.mouseClick(buttons["Сбросить"], Qt.MouseButton.LeftButton)

    assert calls == [("retry", "run-1"), ("reset", "run-1")]
    assert shell.unfinished_runs() == []


def test_export_editor_shell_warns_about_append_duplicates_in_unfinished_runs(qtbot) -> None:
    shell = ExportEditorShell()
    qtbot.addWidget(shell)

    calls: list[str] = []
    shell.set_unfinished_delete_handler(lambda run_id: calls.append(run_id) or True)
    shell.set_unfinished_runs([
        _unfinished_run(
            run_id="append-run",
            write_mode="append",
            total_chunks=4,
            delivered_chunks=2,
            delivered_rows=50,
            total_rows=100,
        )
    ])

    button_texts = [button.text() for button in shell.findChildren(type(shell._gas_setup_wizard_btn))]
    assert "Повторить заново" not in button_texts
    assert "Удалить" in button_texts
    assert any(
        "может создать дубли" in label.text().lower()
        for label in shell.findChildren(type(shell._header._status_summary))
    )

    delete_button = next(button for button in shell.findChildren(type(shell._gas_setup_wizard_btn)) if button.text() == "Удалить")
    qtbot.mouseClick(delete_button, Qt.MouseButton.LeftButton)

    assert calls == ["append-run"]
    assert shell.unfinished_runs() == []


def test_export_editor_shell_applies_gas_setup_wizard_result(qtbot) -> None:
    shell = ExportEditorShell(gas_setup_wizard_factory=_FakeAcceptedWizard)
    qtbot.addWidget(shell)
    shell.set_webhook_url("https://script.google.com/macros/s/old/exec")
    shell.set_gas_options(sheet_name="Exports", write_mode="append")

    changed = []
    shell.changed.connect(lambda: changed.append(True))

    assert shell._gas_setup_wizard_btn.text() == "Подключить таблицу..."
    qtbot.mouseClick(shell._gas_setup_wizard_btn, Qt.MouseButton.LeftButton)

    assert shell.webhook_url() == "https://script.google.com/macros/s/library/exec"
    assert shell.gas_sheet_name() == "Exports"
    assert shell.gas_write_mode() == "append"
    assert changed == [True]


def test_export_editor_shell_ignores_rejected_gas_setup_wizard(qtbot) -> None:
    shell = ExportEditorShell(gas_setup_wizard_factory=_FakeRejectedWizard)
    qtbot.addWidget(shell)
    shell.set_webhook_url("https://script.google.com/macros/s/original/exec")
    shell.set_gas_options(sheet_name="Exports", write_mode="replace_by_date_source")

    qtbot.mouseClick(shell._gas_setup_wizard_btn, Qt.MouseButton.LeftButton)

    assert shell.webhook_url() == "https://script.google.com/macros/s/original/exec"
