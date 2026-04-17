"""Tests for extracted export editor header widget."""

from PySide6.QtCore import Qt

from app.ui.export_editor_header import ExportEditorHeader
from app.ui.theme import Theme


def test_header_roundtrips_name_and_emits_actions(qtbot) -> None:
    header = ExportEditorHeader()
    qtbot.addWidget(header)

    changed = []
    test_requested = []
    run_requested = []
    header.changed.connect(lambda: changed.append(True))
    header.test_requested.connect(lambda: test_requested.append(True))
    header.run_requested.connect(lambda: run_requested.append(True))

    header._name_edit.setText("Nightly export")
    header._name_edit.editingFinished.emit()
    qtbot.mouseClick(header._test_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(header._run_btn, Qt.MouseButton.LeftButton)

    assert header.job_name() == "Nightly export"
    assert changed == [True]
    assert test_requested == [True]
    assert run_requested == [True]


def test_header_updates_status_and_run_button_state(qtbot) -> None:
    header = ExportEditorHeader()
    qtbot.addWidget(header)

    header.set_status("error", "✗ db down")
    header.set_run_enabled(False)

    assert header._status_summary.text() == "✗ db down"
    assert Theme.error in header._status_summary.styleSheet()
    assert header._run_btn.isEnabled() is False
