"""Tests for extracted export editor shell/view."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.core.scheduler import ScheduleMode
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
            "auth_token": "generated-token",
            "scheme_id": "library_v1",
        }


class _FakeRejectedWizard(_FakeAcceptedWizard):
    def exec(self) -> int:
        return int(QDialog.DialogCode.Rejected)


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
        auth_token="secret-token",
        scheme_id="library_v1",
    )
    shell.set_schedule(True, ScheduleMode.HOURLY, "4")

    assert shell.job_name() == "Nightly"
    assert shell.sql_text() == "SELECT 1"
    assert shell.webhook_url() == "https://example.com"
    assert shell.gas_sheet_name() == "Exports"
    assert shell.gas_header_row() == 2
    assert shell.gas_dedupe_key_columns() == ["id", "updated_at"]
    assert shell.gas_auth_token() == "secret-token"
    assert shell.gas_scheme_id() == "library_v1"
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
    shell.set_progress_text("Работаем…")
    shell.set_run_enabled(False)
    shell.prepend_history_entry({"ts": "2026-04-16 12:00:00", "ok": True, "rows": 2})

    assert shell._header._status_summary.text() == "Done"
    assert shell._schedule_panel._progress_lbl.text() == "Работаем…"
    assert shell._header._run_btn.isEnabled() is False
    assert shell.latest_history_entry() is not None


def test_export_editor_shell_applies_gas_setup_wizard_result(qtbot) -> None:
    shell = ExportEditorShell(gas_setup_wizard_factory=_FakeAcceptedWizard)
    qtbot.addWidget(shell)
    shell.set_webhook_url("https://script.google.com/macros/s/old/exec")
    shell.set_gas_options(
        sheet_name="Exports",
        header_row=2,
        dedupe_key_columns=["id"],
        auth_token="old-token",
        scheme_id="",
    )

    changed = []
    shell.changed.connect(lambda: changed.append(True))

    assert shell._gas_setup_wizard_btn.text() == "Подключить таблицу…"
    qtbot.mouseClick(shell._gas_setup_wizard_btn, Qt.MouseButton.LeftButton)

    assert shell.webhook_url() == "https://script.google.com/macros/s/library/exec"
    assert shell.gas_auth_token() == "generated-token"
    assert shell.gas_scheme_id() == "library_v1"
    assert shell.gas_sheet_name() == "Exports"
    assert changed == [True]


def test_export_editor_shell_ignores_rejected_gas_setup_wizard(qtbot) -> None:
    shell = ExportEditorShell(gas_setup_wizard_factory=_FakeRejectedWizard)
    qtbot.addWidget(shell)
    shell.set_webhook_url("https://script.google.com/macros/s/original/exec")
    shell.set_gas_options(
        sheet_name="Exports",
        header_row=2,
        dedupe_key_columns=["id"],
        auth_token="original-token",
        scheme_id="",
    )

    qtbot.mouseClick(shell._gas_setup_wizard_btn, Qt.MouseButton.LeftButton)

    assert shell.webhook_url() == "https://script.google.com/macros/s/original/exec"
    assert shell.gas_auth_token() == "original-token"
    assert shell.gas_scheme_id() == ""
