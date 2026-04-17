"""Tests for extracted test-run dialog shell."""

from PySide6.QtCore import Qt

from app.config import QueryResult
from app.ui.test_run_dialog_shell import TestRunDialogShell as _TestRunDialogShell


def test_test_run_dialog_shell_roundtrips_sql_status_and_results(qtbot) -> None:
    shell = _TestRunDialogShell()
    qtbot.addWidget(shell)

    shell.set_sql_text("SELECT 1")
    shell.set_status("2 строки", color="#111111")
    shell.populate_result(
        QueryResult(
            columns=["name", "count"],
            rows=[("Users", 5), ("Orders", None)],
            count=2,
            duration_ms=14,
        )
    )

    assert shell.sql_text() == "SELECT 1"
    assert shell.status_label().text() == "2 строки"
    assert shell.table().columnCount() == 2
    assert shell.table().rowCount() == 2
    assert shell.table().item(1, 1).text() == ""


def test_test_run_dialog_shell_emits_button_signals(qtbot) -> None:
    shell = _TestRunDialogShell()
    qtbot.addWidget(shell)

    run_requested = []
    close_requested = []
    shell.run_requested.connect(lambda: run_requested.append(True))
    shell.close_requested.connect(lambda: close_requested.append(True))

    qtbot.mouseClick(shell.run_button(), Qt.MouseButton.LeftButton)
    qtbot.mouseClick(shell.close_button(), Qt.MouseButton.LeftButton)

    assert run_requested == [True]
    assert close_requested == [True]
