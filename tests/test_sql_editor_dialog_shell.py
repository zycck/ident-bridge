# -*- coding: utf-8 -*-
"""Tests for extracted SQL editor dialog shell."""

from app.ui.sql_editor_dialog_shell import SqlEditorDialogShell


def test_sql_editor_dialog_shell_exposes_text_and_action_signals(qtbot) -> None:
    shell = SqlEditorDialogShell("SELECT 1", has_formatter=True)
    qtbot.addWidget(shell)

    events: list[str] = []
    shell.accept_requested.connect(lambda: events.append("save"))
    shell.reject_requested.connect(lambda: events.append("cancel"))
    shell.format_requested.connect(lambda: events.append("format"))

    shell.format_button().click()  # type: ignore[union-attr]
    shell.cancel_button().click()
    shell.save_button().click()

    assert shell.text() == "SELECT 1"
    assert events == ["format", "cancel", "save"]


def test_sql_editor_dialog_shell_hides_format_button_when_disabled(qtbot) -> None:
    shell = SqlEditorDialogShell("SELECT 1", has_formatter=False)
    qtbot.addWidget(shell)

    shell.set_text("SELECT 2")

    assert shell.format_button() is None
    assert shell.text() == "SELECT 2"
